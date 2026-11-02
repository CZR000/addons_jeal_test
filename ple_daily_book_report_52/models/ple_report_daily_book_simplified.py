# -*- coding: utf-8 -*-
import base64
import logging
import os
import re
import subprocess
import tempfile

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

from ..reports.report_daily_book_simplified import DailyBookSimplifiedReportExcel
from ..reports.pcge_names import lookup_pcge_name

_logger = logging.getLogger(__name__)

INVOICE_TYPES = ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')
PURCHASE_TYPES = ('in_invoice', 'in_refund')

# Nivel de cuentas fijo: divisionaria (4 digitos del PCGE).
ACCOUNT_DIGITS = 4

# Asientos de destino (AED): el asiento origen apunta a su AED con
# destination_move_id ("Asiento de destino automatico generado por este
# movimiento"). Ojo: origin_move_id es el "Documento Rectificado" de las
# notas de credito, NO el origen de un destino.
DEST_LINK_FIELD = 'destination_move_id'
# Respaldo: referencia "Asiento de Destino: <nombre del origen>". El nombre
# puede tener espacios ("F FACTU/2026/08/0001"), se toma hasta el final.
DEST_REF_RE = re.compile(
    r'^\s*(?:asiento\s+de\s+destino|destino\s+de)\s*:?\s*(.+?)\s*$',
    re.IGNORECASE,
)
REVERSAL_REF_RE = re.compile(r'^\s*reversi[oó]n\s+de\s*:?\s*(.+)$', re.IGNORECASE)


class PleReportDailyBookSimplified(models.Model):
    _name = 'ple.report.daily.book.simplified'
    _description = 'Reporte PLE Libro Diario Simplificado Formato 5.2'
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

    # --- Parametros del formato matricial ---
    pdf_max_cols = fields.Integer(
        string='Cuentas por folio (PDF)', default=10,
        help='Maximo de columnas de cuenta por folio. Los asientos se '
             'agrupan en folios cuyas cuentas no superen este numero; un '
             'asiento con mas cuentas va solo en su folio, con todas sus '
             'columnas (la pagina se reduce a escala).',
    )
    pdf_max_rows = fields.Integer(
        string='Asientos por folio (PDF)', default=30,
    )
    pdf_single_max_cols = fields.Integer(
        string='Cuentas max. para hoja unica (PDF)', default=20,
        help='Si el periodo tiene hasta esta cantidad de cuentas, el PDF '
             'lleva todas las cuentas como columnas fijas en cada folio '
             '(en A3 si superan "Cuentas por folio"). Si tiene mas, cada '
             'folio lleva solo las cuentas de sus asientos. 0 = desactivado.',
    )
    include_destination_analytic = fields.Boolean(
        string='Incluir 79 y 9x de asientos de destino', default=True,
        help='Si se desmarca, se excluyen las cuentas 79 y del elemento 9 '
             'de los asientos de destino (y el asiento si queda vacio).',
    )

    xls_filename = fields.Char()
    xls_binary = fields.Binary(string='Reporte Excel', readonly=True)

    pdf_filename = fields.Char()
    pdf_binary = fields.Binary(string='Reporte PDF', readonly=True)

    @api.depends('company_id', 'date_start', 'date_end')
    def _compute_name(self):
        for rec in self:
            if rec.date_start:
                rec.name = 'Libro Diario 5.2 - %s - %s' % (
                    rec.date_start.strftime('%m/%Y'),
                    rec.company_id.name or '',
                )
            else:
                rec.name = 'Libro Diario 5.2'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_xlsx(self):
        self.ensure_one()
        self._check_params()

        data = self._get_report_data()
        report = DailyBookSimplifiedReportExcel(self, data)
        self.write({
            'xls_binary': base64.b64encode(report.get_content()),
            'xls_filename': report.get_filename(),
        })
        self._mark_generated()

    def action_generate_pdf(self):
        self.ensure_one()
        self._check_params()

        data = self._get_report_data()
        report = DailyBookSimplifiedReportExcel(
            self, data, pdf=True,
            max_cols=self.pdf_max_cols, max_rows=self.pdf_max_rows,
            single_max_cols=self.pdf_single_max_cols,
        )
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
    # Validaciones / helpers
    # ------------------------------------------------------------------
    def _check_dates(self):
        self.ensure_one()
        if not self.date_start or not self.date_end:
            raise ValidationError(_('Debe indicar Fecha Inicio y Fecha Fin.'))
        if self.date_start > self.date_end:
            raise ValidationError(
                _('La Fecha Inicio no puede ser mayor a la Fecha Fin.')
            )

    def _check_params(self):
        self.ensure_one()
        self._check_dates()
        if self.company_id not in self.env.user.company_ids:
            raise UserError(_(
                'No tiene acceso a la compania %s.', self.company_id.name,
            ))
        if (self.pdf_single_max_cols or 0) < 0:
            raise ValidationError(_(
                'Cuentas max. para hoja unica no puede ser negativo.'
            ))
        if (self.pdf_max_cols or 0) < 1 or (self.pdf_max_rows or 0) < 1:
            raise ValidationError(_(
                'Cuentas por folio y Asientos por folio deben ser mayores '
                'a cero.'
            ))

    def _mark_generated(self):
        """Actualiza estado y fecha. Idempotente: la llaman ambos botones,
        no importa el orden ni cuantas veces se regenere."""
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
        """Arma la matriz del Formato 5.2.

        Retorna:
        {
            'digits_label': '4 DÍGITOS',
            'accounts': [{'code': '1041', 'name': '...'}, ...],
            'moves': [
                {'correl': '0001', 'cuo': 'CAMBI/2026/08/0001',
                 'fecha': date, 'glosa': '...',
                 'nets': {'1041': -137.97, ...}},   # solo cuentas movidas
                ...
            ],
        }
        """
        self.ensure_one()
        company = self.company_id
        digits_label = '%s DÍGITOS' % ACCOUNT_DIGITS
        empty = {'digits_label': digits_label, 'accounts': [], 'moves': []}

        # with_company: las reglas multicompania filtran por las companias
        # activas en el selector; sin esto, una compania no activa devuelve
        # 0 asientos aunque existan.
        Move = self.env['account.move'].with_company(company)
        moves = Move.search([
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('date', '>=', self.date_start),
            ('date', '<=', self.date_end),
        ])
        if not moves:
            return empty

        lines_by_move = self._get_lines_by_move(moves)
        account_ids = {acc_id for lines in lines_by_move.values()
                       for acc_id in lines}
        # Odoo 18: el codigo de cuenta depende de la compania; se resuelve
        # por ORM con la compania del reporte (cubre sucursales).
        accounts = self.env['account.account'].with_company(company).browse(
            list(account_ids))
        code_by_account = {a.id: (a.code or '') for a in accounts}
        name_by_code = {}
        for a in accounts:
            if a.code and a.code not in name_by_code:
                name_by_code[a.code] = a.name or ''

        # Asientos de destino y su origen (el origen puede estar fuera del
        # periodo, por eso se busca en toda la compania)
        dest_origin = {}
        if DEST_LINK_FIELD in Move._fields:
            for origin in Move.search([(DEST_LINK_FIELD, 'in', moves.ids)]):
                dest_origin[origin[DEST_LINK_FIELD].id] = origin
        dest_info = {m.id: self._get_destination_info(m, dest_origin)
                     for m in moves}

        ordered = self._order_moves(moves, dest_info)

        result_moves = []
        used_keys = set()
        for move in ordered:
            is_dest, origin_name, _origin = dest_info[move.id]
            nets = {}
            for acc_id, (debit, credit) in lines_by_move.get(move.id, {}).items():
                code = code_by_account.get(acc_id, '')
                if not code:
                    continue
                if (is_dest and not self.include_destination_analytic
                        and (code.startswith('79') or code.startswith('9'))):
                    continue
                key = self._column_key(code)
                nets[key] = nets.get(key, 0.0) + (debit - credit)
            if not nets:
                # Asiento sin lineas imprimibles (p. ej. AED con 79/9x
                # excluidas): no se lista.
                continue
            used_keys.update(nets)
            result_moves.append({
                'cuo': move.name or '',
                'fecha': move.date,
                'glosa': self._compute_glosa(move, is_dest, origin_name),
                'nets': nets,
            })

        width = max(4, len(str(len(result_moves))))
        for idx, m in enumerate(result_moves, start=1):
            m['correl'] = str(idx).zfill(width)

        codes = sorted(used_keys)
        names = self._resolve_column_names(codes, name_by_code)
        return {
            'digits_label': digits_label,
            'accounts': [{'code': c, 'name': names.get(c, '')} for c in codes],
            'moves': result_moves,
        }

    # ------------------------------------------------------------------
    # Helpers de data
    # ------------------------------------------------------------------
    def _column_key(self, code):
        return code[:ACCOUNT_DIGITS]

    def _get_lines_by_move(self, moves):
        """{move_id: {account_id: (debit, credit)}} en moneda de la compania."""
        self.env.cr.execute("""
            SELECT aml.move_id, aml.account_id,
                   COALESCE(SUM(aml.debit), 0.0),
                   COALESCE(SUM(aml.credit), 0.0)
            FROM account_move_line aml
            WHERE aml.move_id IN %s
              AND aml.account_id IS NOT NULL
            GROUP BY aml.move_id, aml.account_id
        """, (tuple(moves.ids),))
        result = {}
        for move_id, account_id, debit, credit in self.env.cr.fetchall():
            result.setdefault(move_id, {})[account_id] = (
                float(debit or 0.0), float(credit or 0.0),
            )
        return result

    def _get_destination_info(self, move, dest_origin):
        """(es_destino, nombre_origen, asiento_origen o vacio).

        dest_origin: {id_AED: asiento_origen} armado desde
        destination_move_id de los asientos origen.
        """
        Move = self.env['account.move']
        origin = dest_origin.get(move.id)
        if origin:
            return True, origin.name or '', origin
        # La reversion de un destino ("Reversión de: Asiento de Destino: X")
        # es una reversion, no un destino.
        if move.reversed_entry_id or REVERSAL_REF_RE.match(move.ref or ''):
            return False, '', Move
        match = DEST_REF_RE.match(move.ref or '')
        if match:
            return True, match.group(1).strip(), Move
        journal_code = (move.journal_id.code or '').upper()
        if journal_code.startswith('AED') or (move.name or '').startswith('AED/'):
            return True, '', Move
        return False, '', Move

    def _order_moves(self, moves, dest_info):
        """Por fecha y numero; cada asiento de destino va inmediatamente
        despues de su asiento origen (si el origen esta en el periodo)."""
        base = moves.sorted(key=lambda m: (m.date, m.name or '', m.id))
        by_id = {m.id: m for m in base}
        by_name = {}
        for m in base:
            by_name.setdefault(m.name, m)

        children = {}
        attached = set()
        for m in base:
            is_dest, origin_name, origin = dest_info[m.id]
            if not is_dest:
                continue
            parent = None
            if origin and origin.id in by_id:
                parent = by_id[origin.id]
            elif origin_name and origin_name in by_name:
                parent = by_name[origin_name]
            if parent and parent.id != m.id:
                children.setdefault(parent.id, []).append(m)
                attached.add(m.id)

        ordered = []
        visited = set()

        def add(m):
            if m.id in visited:
                return
            visited.add(m.id)
            ordered.append(m)
            for child in children.get(m.id, []):
                add(child)

        for m in base:
            if m.id not in attached:
                add(m)
        # Destinos cuyo origen forma un ciclo o no quedo agregado
        for m in base:
            add(m)
        return ordered

    def _compute_glosa(self, move, is_dest, origin_name):
        """Glosa segun tipo de asiento (notas al programador 3.2)."""
        if is_dest:
            if origin_name:
                return 'Destino de %s' % origin_name
            return move.ref or 'Asiento de destino'

        if move.move_type in INVOICE_TYPES:
            if move.move_type in PURCHASE_TYPES:
                # Compras: la serie-numero del proveedor esta en ref
                # (F001-00025414); l10n_latam_document_number repite el
                # nombre interno (F FACTU/2026/08/0001).
                kind = 'Compra'
                number = (move.ref
                          or getattr(move, 'l10n_latam_document_number', False)
                          or move.name or '')
            else:
                kind = 'Venta'
                number = (getattr(move, 'l10n_latam_document_number', False)
                          or move.name or '')
            partner = move.partner_id.name or ''
            return ('%s %s - %s' % (kind, number, partner)).strip(' -')

        if move.reversed_entry_id:
            return 'Reversión %s' % (move.reversed_entry_id.name or '')
        match = REVERSAL_REF_RE.match(move.ref or '')
        if match:
            return 'Reversión %s' % match.group(1).strip()

        exchange_journal = move.company_id.currency_exchange_journal_id
        if (exchange_journal and move.journal_id == exchange_journal
                and not move.ref):
            return 'Diferencia de cambio al %s' % move.date.strftime('%d/%m/%Y')

        if 'asset_id' in move._fields and move.asset_id:
            return 'Depreciación del mes - %s' % (move.asset_id.name or '')

        return move.ref or move.journal_id.name or move.name or ''

    def _resolve_column_names(self, codes, name_by_code):
        """Nombre por columna: 1) account.group, 2) tabla PCGE interna,
        3) primera cuenta de la compania con ese prefijo."""
        company = self.company_id
        names = {}
        if not codes:
            return names

        company_ids = (company.parent_ids.ids
                       if 'parent_ids' in company._fields else company.ids)
        groups = self.env['account.group'].with_company(company).search([
            ('code_prefix_start', 'in', codes),
            ('company_id', 'in', company_ids),
        ])
        group_names = {}
        for g in groups:
            prefix = g.code_prefix_start
            exact = not g.code_prefix_end or g.code_prefix_end == prefix
            if prefix not in group_names or exact:
                group_names[prefix] = g.name or ''

        for code in codes:
            name = group_names.get(code) or lookup_pcge_name(code)
            if not name:
                first = min((c for c in name_by_code if c.startswith(code)),
                            default=None)
                name = name_by_code.get(first, '') if first else ''
            names[code] = name
        return names
