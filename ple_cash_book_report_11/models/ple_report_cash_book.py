import base64
import logging
import os
import subprocess
import tempfile
from calendar import monthrange
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

from ..reports.report_cash_book import CashBookReportExcel, MONTHS_ES

_logger = logging.getLogger(__name__)


# Cuentas de efectivo consideradas por el reporte (hardcoded para JE-AL).
# Editar aqui si cambia el set de cuentas de caja/bancos a incluir.
CASH_ACCOUNT_CODES = [
    '1010000',
    '1010001',
    '1020000',
    '1020001',
    '1031000',
]


# Mapeo SUNAT tabla 10 -> abreviatura mostrada en columna TD.
SUNAT_DOC_TYPE_MAP = {
    '01': 'FT',
    '02': 'RH',
    '03': 'BV',
    '04': 'LT',
    '05': 'BA',
    '07': 'NC',
    '08': 'ND',
    '09': 'GR',
    '12': 'TK',
    '13': 'DB',
    '14': 'RS',
}


INVOICE_TYPES = ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')


class PleReportCashBook(models.Model):
    _name = 'ple.report.cash.book'
    _description = 'Reporte PLE Libro Caja y Bancos Formato 1.1'
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
                rec.name = 'Libro Caja 1.1 - %s - %s' % (
                    rec.date_start.strftime('%m/%Y'),
                    rec.company_id.name or '',
                )
            else:
                rec.name = 'Libro Caja 1.1'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_xlsx(self):
        self.ensure_one()
        self._check_dates()

        data = self._get_report_data()
        report = CashBookReportExcel(self, data)
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
            report = CashBookReportExcel(self, data)
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
    # Helpers comunes
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
        """Actualiza estado y fecha. Idempotente: la llaman ambos botones."""
        self.write({
            'date_generated': fields.Date.today(),
            'state': 'confirmed',
        })

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

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _get_report_data(self):
        """Arma la estructura del reporte segmentada por mes y cuenta.

        Retorna una lista de meses; cada mes tiene una lista de cuentas de
        efectivo con su saldo inicial y sus filas expandidas por
        contrapartida.
        """
        self.ensure_one()

        months = self._get_months_in_range()
        accounts = self._get_report_accounts()
        if not accounts:
            _logger.warning(
                'PLE Libro Caja 1.1: no se encontraron las cuentas '
                'hardcoded %s en la compania %s',
                CASH_ACCOUNT_CODES, self.company_id.name,
            )
            return []
        if not months:
            return []

        initial_balances = self._get_initial_balances(accounts)
        lines_by_month_account = self._get_lines_grouped(accounts)

        running = {acc.id: initial_balances.get(acc.id, 0.0) for acc in accounts}
        counters = {}         # {(cl, yyyymm): count}
        move_registros = {}   # {move_id: nro_registro} memoizado global

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
                saldo_ini = running.get(account.id, 0.0)
                cash_lines = lines_by_month_account.get(
                    (month_key, account.id), []
                )

                expanded_rows = []
                saldo = saldo_ini

                for line_10 in cash_lines:
                    move = line_10.move_id

                    # Asignar NUMERO REGISTRO por asiento (memoizado)
                    if move.id not in move_registros:
                        cl = self._get_journal_cl(move.journal_id)
                        yyyymm = move.date.strftime('%Y%m')
                        key = (cl, yyyymm)
                        counters[key] = counters.get(key, 0) + 1
                        move_registros[move.id] = '%s-%08d' % (
                            cl, counters[key]
                        )
                    nro_registro = move_registros[move.id]

                    descripcion = (move.ref or line_10.name or move.name or '')[:200]
                    mon = self._compute_mon(line_10)

                    # Contrapartidas: todas las lineas del asiento salvo la
                    # linea actual de la cuenta de caja
                    contras = move.line_ids - line_10

                    for contra in contras:
                        td, nro_ref, fecha_ref = self._compute_doc_info(
                            line_10, contra,
                        )
                        deudor = contra.credit
                        acreedor = contra.debit
                        saldo = saldo + deudor - acreedor

                        expanded_rows.append({
                            'nro_registro': nro_registro,
                            'fecha_op': move.date,
                            'descripcion': descripcion,
                            'td': td,
                            'nro_ref': nro_ref,
                            'fecha_ref': fecha_ref,
                            'mon': mon,
                            'contra_code': contra.account_id.code or '',
                            'contra_name': contra.account_id.name or '',
                            'deudor': deudor,
                            'acreedor': acreedor,
                            'saldo': saldo,
                        })

                # Cuentas sin movimiento y sin saldo previo se omiten
                if not expanded_rows and abs(saldo_ini) < 0.005:
                    continue

                month_block['accounts'].append({
                    'account_code': account.code or '',
                    'account_name': account.name or '',
                    'saldo_anterior': saldo_ini,
                    'lines': expanded_rows,
                })

                running[account.id] = saldo

            if month_block['accounts']:
                result.append(month_block)

        return result

    # ------------------------------------------------------------------
    # Helpers de data
    # ------------------------------------------------------------------
    def _get_months_in_range(self):
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
        AccountAccount = self.env['account.account'].with_company(self.company_id)
        accounts = AccountAccount.search([
            ('code', 'in', CASH_ACCOUNT_CODES),
            ('company_ids', 'in', self.company_id.id),
        ])
        return accounts.sorted(lambda a: a.code or '')

    def _get_initial_balances(self, accounts):
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

    def _get_lines_grouped(self, accounts):
        """Retorna {(year, month, account_id): [account.move.line, ...]}."""
        if not accounts:
            return {}
        lines = self.env['account.move.line'].with_company(
            self.company_id
        ).with_context(
            allowed_company_ids=[self.company_id.id]
        ).search([
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_start),
            ('date', '<=', self.date_end),
            ('account_id', 'in', accounts.ids),
        ], order='account_id, date, move_id, id')

        result = {}
        for line in lines:
            key = ((line.date.year, line.date.month), line.account_id.id)
            result.setdefault(key, []).append(line)
        return result

    def _get_journal_cl(self, journal):
        """CL del subdiario: prefiere ple_book_code si el modulo 5.1 lo
        instalo, sino cae a journal.code."""
        cl = getattr(journal, 'ple_book_code', None) or journal.code or ''
        return str(cl or '').strip()

    def _compute_mon(self, line):
        currency = line.currency_id or line.move_id.currency_id
        code = (currency.name or '').upper() if currency else ''
        if code == 'PEN':
            return 'MN'
        if code == 'USD':
            return 'US'
        return (code[:2] or 'MN')

    def _compute_doc_info(self, line_10, contra_line):
        """Devuelve (TD, NUMERO, FECHA) del documento asociado a la
        contrapartida.

        - Si contra_line esta reconciliada con una factura:
          TD = abreviatura SUNAT, NUMERO = factura.name,
          FECHA = factura.invoice_date (fallback factura.date).
        - Sino: TD = 'OT', NUMERO = fecha del asiento DDMMYYYY,
          FECHA = fecha del asiento.
        """
        invoice = self._find_reconciled_invoice(contra_line)
        if invoice:
            doc_type_id = getattr(invoice, 'l10n_latam_document_type_id', None)
            code = (doc_type_id.code or '') if doc_type_id else ''
            td = SUNAT_DOC_TYPE_MAP.get(code, 'OT')
            nro = invoice.name or ''
            fecha = invoice.invoice_date or invoice.date
            return (td, nro, fecha)
        d = line_10.move_id.date
        return ('OT', d.strftime('%d%m%Y'), d)

    def _find_reconciled_invoice(self, line):
        """Recorre las reconciliaciones de la linea y devuelve la primera
        contraparte que sea factura (out_invoice / in_invoice /
        out_refund / in_refund)."""
        Move = self.env['account.move']
        counterpart = Move
        for partial in line.matched_debit_ids:
            counterpart |= partial.debit_move_id.move_id
        for partial in line.matched_credit_ids:
            counterpart |= partial.credit_move_id.move_id
        counterpart -= line.move_id
        invoices = counterpart.filtered(lambda m: m.move_type in INVOICE_TYPES)
        return invoices[:1]
