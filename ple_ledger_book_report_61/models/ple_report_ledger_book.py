import base64
import os
import subprocess
import tempfile
from calendar import monthrange
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from ..reports.report_ledger_book import LedgerBookReportExcel, MONTHS_ES


class PleReportLedgerBook(models.Model):
    _name = 'ple.report.ledger.book'
    _description = 'Reporte PLE Libro Mayor Formato 6.1'
    _order = 'date_start desc, id desc'

    name = fields.Char(
        compute='_compute_name', store=True, string='Nombre',
    )
    company_id = fields.Many2one(
        'res.company', string='Compania',
        required=True, default=lambda self: self.env.company,
    )
    date_start = fields.Date(string='Fecha Inicio', required=True)
    date_end = fields.Date(string='Fecha Fin', required=True)
    date_generated = fields.Date(string='Generado el', readonly=True)

    account_ids = fields.Many2many(
        'account.account',
        string='Cuentas especificas',
        domain="[('company_ids', 'in', company_id)]",
        help='Si se deja vacio, se incluyen todas las cuentas con saldo '
             'previo o movimiento en el periodo.',
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('confirmed', 'Generado'),
        ],
        string='Estado', default='draft',
    )

    xls_filename = fields.Char()
    xls_binary = fields.Binary(string='Reporte Excel', readonly=True)

    pdf_filename = fields.Char()
    pdf_binary = fields.Binary(string='Reporte PDF', readonly=True)

    @api.depends('company_id', 'date_start', 'date_end')
    def _compute_name(self):
        for rec in self:
            if rec.date_start:
                rec.name = 'Libro Mayor 6.1 - %s - %s' % (
                    rec.date_start.strftime('%m/%Y'),
                    rec.company_id.name or '',
                )
            else:
                rec.name = 'Libro Mayor 6.1'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_xlsx(self):
        self.ensure_one()
        self._check_dates()

        data = self._get_report_data()
        report = LedgerBookReportExcel(self, data)
        self.write({
            'xls_binary': base64.b64encode(report.get_content()),
            'xls_filename': report.get_filename(),
        })
        self._mark_generated()

    def action_generate_pdf(self):
        self.ensure_one()
        self._check_dates()

        # Reutiliza el XLSX ya generado; si no existe, lo genera al vuelo.
        if self.xls_binary:
            xlsx_bytes = base64.b64decode(self.xls_binary)
            pdf_name = (self.xls_filename or 'reporte.xlsx').replace('.xlsx', '.pdf')
        else:
            data = self._get_report_data()
            report = LedgerBookReportExcel(self, data)
            xlsx_bytes = report.get_content()
            pdf_name = report.get_filename().replace('.xlsx', '.pdf')

        pdf_content = self._xlsx_to_pdf(xlsx_bytes)

        self.write({
            'pdf_binary': base64.b64encode(pdf_content),
            'pdf_filename': pdf_name,
        })
        self._mark_generated()

    def action_reset_to_draft(self):
        self.write({
            'state': 'draft',
            'xls_binary': False,
            'xls_filename': False,
            'pdf_binary': False,
            'pdf_filename': False,
            'date_generated': False,
        })

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _get_report_data(self):
        """Arma la estructura de datos del reporte segmentada por mes.

        Retorna una lista de meses, cada uno con sus cuentas y bloques:
        [
            {
                'label': 'ENERO DE 2024',
                'date_from': date(2024, 1, 1),
                'date_to': date(2024, 1, 31),
                'accounts': [
                    {
                        'account_code': '101101',
                        'account_name': 'CAJA M.N.',
                        'saldo_anterior': float,
                        'lines': [dict, ...],
                        'total_debit': float,
                        'total_credit': float,
                        'saldo_actual': float,
                    },
                    ...
                ],
            },
            ...
        ]
        """
        self.ensure_one()

        months = self._get_months_in_range()
        accounts = self._get_report_accounts()
        if not accounts or not months:
            return []

        initial_balances = self._get_initial_balances(accounts)
        movements = self._get_movements_grouped(accounts)

        # Saldos que van rodando mes a mes
        running = {acc.id: initial_balances.get(acc.id, 0.0) for acc in accounts}

        result = []
        for month_from, month_to, month_label in months:
            month_key = (month_from.year, month_from.month)
            month_block = {
                'label': month_label,
                'date_from': month_from,
                'date_to': month_to,
                'accounts': [],
            }

            for account in accounts:
                saldo_ant = running.get(account.id, 0.0)
                lines = movements.get((month_key, account.id), [])

                # Si no hay movimiento en el mes y no hay saldo previo,
                # se omite la cuenta para este mes.
                if not lines and abs(saldo_ant) < 0.005:
                    continue

                total_debit = sum(l['debit'] for l in lines)
                total_credit = sum(l['credit'] for l in lines)
                saldo_act = saldo_ant + total_debit - total_credit

                month_block['accounts'].append({
                    'account_code': account.code or '',
                    'account_name': account.name or '',
                    'saldo_anterior': saldo_ant,
                    'lines': lines,
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'saldo_actual': saldo_act,
                })

                running[account.id] = saldo_act

            if month_block['accounts']:
                result.append(month_block)

        return result

    # ------------------------------------------------------------------
    # Helpers de data
    # ------------------------------------------------------------------
    def _check_dates(self):
        self.ensure_one()
        if not self.date_start or not self.date_end:
            raise ValidationError(_('Debe indicar Fecha Inicio y Fecha Fin.'))
        if self.date_start > self.date_end:
            raise ValidationError(
                _('La Fecha Inicio no puede ser mayor a la Fecha Fin.')
            )

    def _mark_generated(self):
        """Actualiza estado y fecha. Idempotente: la llaman ambos botones,
        no importa el orden ni cuantas veces se regenere."""
        self.write({
            'date_generated': fields.Date.today(),
            'state': 'confirmed',
        })

    def _get_months_in_range(self):
        """Devuelve la lista de meses (from, to, label) que cubren el rango.

        Los limites de cada mes se recortan al rango del reporte.
        """
        result = []
        year = self.date_start.year
        month = self.date_start.month
        end_year = self.date_end.year
        end_month = self.date_end.month

        while (year, month) <= (end_year, end_month):
            last_day = monthrange(year, month)[1]
            month_first = date(year, month, 1)
            month_last = date(year, month, last_day)
            actual_from = max(month_first, self.date_start)
            actual_to = min(month_last, self.date_end)
            result.append((
                actual_from,
                actual_to,
                '%s DE %d' % (MONTHS_ES.get(month, ''), year),
            ))
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
        return result

    def _get_report_accounts(self):
        """Universo de cuentas a incluir en el reporte.

        - Si account_ids esta definido, se usa esa lista tal cual.
        - Caso contrario, cuentas con movimiento en el rango UNION cuentas
          con saldo distinto de cero al inicio del rango.
        """
        AccountAccount = self.env['account.account'].with_company(self.company_id)

        if self.account_ids:
            return self.account_ids.sorted(lambda a: a.code or '')

        # Cuentas con movimiento en el rango
        self.env.cr.execute("""
            SELECT DISTINCT aml.account_id
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.company_id = %s
              AND am.state = 'posted'
              AND am.date BETWEEN %s AND %s
        """, (self.company_id.id, self.date_start, self.date_end))
        ids_movement = {r[0] for r in self.env.cr.fetchall()}

        # Cuentas con saldo != 0 al date_start - 1
        self.env.cr.execute("""
            SELECT aml.account_id
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.company_id = %s
              AND am.state = 'posted'
              AND am.date < %s
            GROUP BY aml.account_id
            HAVING ABS(COALESCE(SUM(aml.debit - aml.credit), 0)) > 0.005
        """, (self.company_id.id, self.date_start))
        ids_balance = {r[0] for r in self.env.cr.fetchall()}

        all_ids = ids_movement | ids_balance
        return AccountAccount.browse(all_ids).sorted(lambda a: a.code or '')

    def _get_initial_balances(self, accounts):
        """Saldo neto (debit - credit) de cada cuenta al date_start - 1."""
        if not accounts:
            return {}
        self.env.cr.execute("""
            SELECT
                aml.account_id,
                COALESCE(SUM(aml.debit - aml.credit), 0.0) AS balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.company_id = %s
              AND am.state = 'posted'
              AND am.date < %s
              AND aml.account_id IN %s
            GROUP BY aml.account_id
        """, (self.company_id.id, self.date_start, tuple(accounts.ids)))
        return {r[0]: float(r[1] or 0.0) for r in self.env.cr.fetchall()}

    def _get_movements_grouped(self, accounts):
        """Devuelve {(year, month, account_id): [line_dict, ...]}."""
        if not accounts:
            return {}

        lines = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_start),
            ('date', '<=', self.date_end),
            ('account_id', 'in', accounts.ids),
        ], order='account_id, date, move_id, id')

        result = {}
        for line in lines:
            key = ((line.date.year, line.date.month), line.account_id.id)
            result.setdefault(key, []).append(self._line_to_dict(line))
        return result

    def _line_to_dict(self, line):
        nro_ref, fecha_ref = self._compute_ref(line)
        move = line.move_id
        descripcion = move.ref or line.name or move.name or ''
        return {
            'fecha_op': line.date,
            'nro_comprobante': move.name or '',
            'descripcion': descripcion[:200],
            'td': self._compute_td(line),
            'nro_ref': nro_ref,
            'fecha_ref': fecha_ref,
            'anexo': (line.partner_id.vat or '') if line.partner_id else '',
            'debit': line.debit,
            'credit': line.credit,
        }

    def _compute_td(self, line):
        """Devuelve el codigo TD segun las reglas acordadas.

        - NC si el asiento es Nota de Credito (SUNAT 07)
        - ND si es Nota de Debito (SUNAT 08)
        - TB si el diario del asiento es de tipo banco
        - OT en el resto de casos
        """
        move = line.move_id
        doc_code = ''
        if hasattr(move, 'l10n_latam_document_type_id') and \
                move.l10n_latam_document_type_id:
            doc_code = move.l10n_latam_document_type_id.code or ''
        if doc_code == '07':
            return 'NC'
        if doc_code == '08':
            return 'ND'
        if move.journal_id.type == 'bank':
            return 'TB'
        return 'OT'

    def _compute_ref(self, line):
        """Devuelve (nro_ref, fecha_ref) para las columnas del Documento
        Referencia.

        Si la linea esta reconciliada con una factura, se toman el nombre y
        la fecha de emision de esa factura. Caso contrario, se rellena con
        la fecha del asiento en formato DDMMYYYY y esa misma fecha.
        """
        invoice = self._find_reconciled_invoice(line)
        if invoice:
            return (
                invoice.name or '',
                invoice.invoice_date or invoice.date,
            )
        d = line.move_id.date
        return (d.strftime('%d%m%Y'), d)

    def _find_reconciled_invoice(self, line):
        """Busca en la reconciliacion de la linea una factura contraparte.

        En Odoo 18:
          - matched_debit_ids: partials donde ESTA linea es el credit_move_id
            (contraparte = partial.debit_move_id.move_id)
          - matched_credit_ids: partials donde ESTA linea es el debit_move_id
            (contraparte = partial.credit_move_id.move_id)
        """
        Move = self.env['account.move']
        counterpart = Move
        for partial in line.matched_debit_ids:
            counterpart |= partial.debit_move_id.move_id
        for partial in line.matched_credit_ids:
            counterpart |= partial.credit_move_id.move_id

        invoice_types = ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')
        invoices = counterpart.filtered(lambda m: m.move_type in invoice_types)
        return invoices[:1]

    def _xlsx_to_pdf(self, xlsx_bytes):
        """Convierte bytes de un XLSX a PDF usando LibreOffice headless."""
        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = os.path.join(tmp, 'report.xlsx')
            with open(xlsx_path, 'wb') as fh:
                fh.write(xlsx_bytes)

            profile = 'file://%s' % os.path.join(tmp, 'profile')
            result = None
            for binary in ('libreoffice', 'soffice'):
                try:
                    result = subprocess.run(
                        [
                            binary,
                            '-env:UserInstallation=%s' % profile,
                            '--headless', '--convert-to',
                            'pdf:calc_pdf_Export',
                            '--outdir', tmp, xlsx_path,
                        ],
                        capture_output=True, timeout=110,
                    )
                    break
                except FileNotFoundError:
                    continue
                except subprocess.TimeoutExpired:
                    raise UserError(_(
                        'La conversion a PDF excedio el tiempo limite. '
                        'El reporte puede ser demasiado grande.'
                    ))

            if result is None:
                raise UserError(
                    _('LibreOffice no esta disponible en el servidor.')
                )

            pdf_path = os.path.join(tmp, 'report.pdf')
            if result.returncode != 0 or not os.path.exists(pdf_path):
                err = (result.stderr or b'').decode('utf-8', 'replace')[:500]
                raise UserError(
                    _('No se pudo generar el PDF.\n%s')
                    % (err or 'Error desconocido de LibreOffice.')
                )

            with open(pdf_path, 'rb') as fh:
                return fh.read()
