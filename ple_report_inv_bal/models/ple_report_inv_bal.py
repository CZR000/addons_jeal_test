import base64
import logging
import os
import subprocess
import tempfile
from datetime import date, timedelta
from io import BytesIO

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression

from ..reports.report_inv_bal_base import xlsxwriter

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Catalogo de formatos del Libro de Inventarios y Balances.
# El sufijo de dos digitos (01..20) se usa en los nombres de campo y de
# accion: xls_binary_<nn>, pdf_binary_<nn>, action_generate_<nn>.
# ---------------------------------------------------------------------------
FORMATOS = [
    ('01', '3.1',  'Balance General'),
    ('02', '3.2',  'Efectivo y Equivalente al Efectivo (Cuenta 10)'),
    ('03', '3.3',  'Clientes (Cuenta 12)'),
    ('04', '3.4',  'Cuentas por Cobrar a Accionistas (Socios) y Personal (Cuenta 14)'),
    ('05', '3.5',  'Cuentas por Cobrar Diversas (Cuenta 16)'),
    ('06', '3.6',  'Estimacion de Cuentas de Cobranza Dudosa (Cuenta 19)'),
    ('07', '3.7',  'Mercaderias y Productos Terminados (Cuentas 20 y 21)'),
    ('08', '3.8',  'Inversiones mobiliarias (Cuenta 30)'),
    ('09', '3.9',  'Intangibles (Cuenta 34)'),
    ('10', '3.10', 'Tributos por Pagar (Cuenta 40)'),
    ('11', '3.11', 'Remuneraciones y Participaciones por Pagar (Cuenta 41)'),
    ('12', '3.12', 'Proveedores (Cuenta 42)'),
    ('13', '3.13', 'Cuentas por Pagar Diversas - Terceros y Relacionadas (Cuentas 46 y 47)'),
    ('14', '3.14', 'Beneficios Sociales de los Trabajadores (Cuenta 47)'),
    ('15', '3.15', 'Ganancias Diferidas (Cuenta 49)'),
    ('17', '3.17', 'Balance de Comprobacion (Anexo 1)'),
    ('18', '3.18', 'Estado de Flujos de Efectivo'),
    ('19', '3.19', 'Estado de Cambios en el Patrimonio Neto'),
    ('20', '3.20', 'Estado de Ganancias y Perdidas por Funcion'),
]

def _default_date_start(env):
    """Primer dia del mes anterior a la fecha actual."""
    today = fields.Date.context_today(env.user)
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def _default_date_end(env):
    """Ultimo dia del mes anterior a la fecha actual."""
    today = fields.Date.context_today(env.user)
    return today.replace(day=1) - timedelta(days=1)


class PleReportInvBal(models.Model):

    _name = 'ple.report.inv.bal.book'

    _description = 'Reporte PLE Libro de Inventarios y Balances - Fisico (3.1 a 3.20)'

    _order = 'date_end desc, date_start desc, id desc'

    _sql_constraints = [
        ('period_company_uniq',
         'unique(company_id, date_start, date_end)',
         'Ya existe un reporte para esta compañía y rango de fechas.'),
    ]

    name = fields.Char(compute='_compute_name', store=True, string='Nombre')

    company_id = fields.Many2one(
        'res.company', string='Compania',
        required=True, default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.user.company_ids.ids)],
    )

    date_start = fields.Date(
        string='Fecha Inicio', required=True,
        default=lambda self: _default_date_start(self.env),
    )

    date_end = fields.Date(
        string='Fecha Fin', required=True,
        default=lambda self: _default_date_end(self.env),
    )

    date_generated = fields.Date(string='Generado el', readonly=True)

    show_by_format = fields.Boolean(
        string='Generar por formato', default=False,
        help='Muestra las secciones de cada formato (3.1 a 3.20) para '
             'generarlos uno por uno.',
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('confirmed', 'Generado'),
        ],
        string='Estado', default='draft',
    )

    closing_journal_ids = fields.Many2many(
        'account.journal', 'ple_inv_bal_book_closing_journal_rel',
        'report_id', 'journal_id',
        string='Diarios de cierre',
        compute='_compute_closing_opening_journals', store=True, readonly=False,
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
        help='Asientos de cierre del ejercicio. Los de estos diarios con fecha '
             'igual a la Fecha Fin no se consideran, para mostrar los saldos '
             'antes del cierre. En los estados del periodo (3.18 a 3.20) '
             'tampoco se consideran los que caen dentro del periodo.',
    )

    opening_journal_ids = fields.Many2many(
        'account.journal', 'ple_inv_bal_book_opening_journal_rel',
        'report_id', 'journal_id',
        string='Diarios de apertura',
        compute='_compute_closing_opening_journals', store=True, readonly=False,
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
        help='Asientos de apertura (reapertura de saldos). En los estados del '
             'periodo (3.17 a 3.20) se tratan como saldo inicial y no como '
             'movimiento, flujo o resultado del periodo.',
    )

    # -- Campos de archivo por formato (Excel y PDF por cada uno de 3.1 a 3.20) --
    xls_filename_01 = fields.Char()

    xls_binary_01 = fields.Binary(string='Excel 3.1', readonly=True)

    pdf_filename_01 = fields.Char()

    pdf_binary_01 = fields.Binary(string='PDF 3.1', readonly=True)

    xls_filename_02 = fields.Char()

    xls_binary_02 = fields.Binary(string='Excel 3.2', readonly=True)

    pdf_filename_02 = fields.Char()

    pdf_binary_02 = fields.Binary(string='PDF 3.2', readonly=True)

    xls_filename_03 = fields.Char()

    xls_binary_03 = fields.Binary(string='Excel 3.3', readonly=True)

    pdf_filename_03 = fields.Char()

    pdf_binary_03 = fields.Binary(string='PDF 3.3', readonly=True)

    xls_filename_04 = fields.Char()

    xls_binary_04 = fields.Binary(string='Excel 3.4', readonly=True)

    pdf_filename_04 = fields.Char()

    pdf_binary_04 = fields.Binary(string='PDF 3.4', readonly=True)

    xls_filename_05 = fields.Char()

    xls_binary_05 = fields.Binary(string='Excel 3.5', readonly=True)

    pdf_filename_05 = fields.Char()

    pdf_binary_05 = fields.Binary(string='PDF 3.5', readonly=True)

    xls_filename_06 = fields.Char()

    xls_binary_06 = fields.Binary(string='Excel 3.6', readonly=True)

    pdf_filename_06 = fields.Char()

    pdf_binary_06 = fields.Binary(string='PDF 3.6', readonly=True)

    xls_filename_07 = fields.Char()

    xls_binary_07 = fields.Binary(string='Excel 3.7', readonly=True)

    pdf_filename_07 = fields.Char()

    pdf_binary_07 = fields.Binary(string='PDF 3.7', readonly=True)

    xls_filename_08 = fields.Char()

    xls_binary_08 = fields.Binary(string='Excel 3.8', readonly=True)

    pdf_filename_08 = fields.Char()

    pdf_binary_08 = fields.Binary(string='PDF 3.8', readonly=True)

    xls_filename_09 = fields.Char()

    xls_binary_09 = fields.Binary(string='Excel 3.9', readonly=True)

    pdf_filename_09 = fields.Char()

    pdf_binary_09 = fields.Binary(string='PDF 3.9', readonly=True)

    xls_filename_10 = fields.Char()

    xls_binary_10 = fields.Binary(string='Excel 3.10', readonly=True)

    pdf_filename_10 = fields.Char()

    pdf_binary_10 = fields.Binary(string='PDF 3.10', readonly=True)

    xls_filename_11 = fields.Char()

    xls_binary_11 = fields.Binary(string='Excel 3.11', readonly=True)

    pdf_filename_11 = fields.Char()

    pdf_binary_11 = fields.Binary(string='PDF 3.11', readonly=True)

    xls_filename_12 = fields.Char()

    xls_binary_12 = fields.Binary(string='Excel 3.12', readonly=True)

    pdf_filename_12 = fields.Char()

    pdf_binary_12 = fields.Binary(string='PDF 3.12', readonly=True)

    xls_filename_13 = fields.Char()

    xls_binary_13 = fields.Binary(string='Excel 3.13', readonly=True)

    pdf_filename_13 = fields.Char()

    pdf_binary_13 = fields.Binary(string='PDF 3.13', readonly=True)

    xls_filename_14 = fields.Char()

    xls_binary_14 = fields.Binary(string='Excel 3.14', readonly=True)

    pdf_filename_14 = fields.Char()

    pdf_binary_14 = fields.Binary(string='PDF 3.14', readonly=True)

    xls_filename_15 = fields.Char()

    xls_binary_15 = fields.Binary(string='Excel 3.15', readonly=True)

    pdf_filename_15 = fields.Char()

    pdf_binary_15 = fields.Binary(string='PDF 3.15', readonly=True)

    xls_filename_17 = fields.Char()

    xls_binary_17 = fields.Binary(string='Excel 3.17', readonly=True)

    pdf_filename_17 = fields.Char()

    pdf_binary_17 = fields.Binary(string='PDF 3.17', readonly=True)

    xls_filename_18 = fields.Char()

    xls_binary_18 = fields.Binary(string='Excel 3.18', readonly=True)

    pdf_filename_18 = fields.Char()

    pdf_binary_18 = fields.Binary(string='PDF 3.18', readonly=True)

    xls_filename_19 = fields.Char()

    xls_binary_19 = fields.Binary(string='Excel 3.19', readonly=True)

    pdf_filename_19 = fields.Char()

    pdf_binary_19 = fields.Binary(string='PDF 3.19', readonly=True)

    xls_filename_20 = fields.Char()

    xls_binary_20 = fields.Binary(string='Excel 3.20', readonly=True)

    pdf_filename_20 = fields.Char()

    pdf_binary_20 = fields.Binary(string='PDF 3.20', readonly=True)

    # -- Libro completo (los 19 formatos en un solo Excel y un solo PDF) --
    xls_filename_all = fields.Char()

    xls_binary_all = fields.Binary(string='Excel Libro Completo', readonly=True)

    pdf_filename_all = fields.Char()

    pdf_binary_all = fields.Binary(string='PDF Libro Completo', readonly=True)

    @api.constrains('date_start', 'date_end')
    def _check_date_range(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_start > rec.date_end:
                raise ValidationError(_(
                    'La Fecha Inicio no puede ser posterior a la Fecha Fin.'
                ))

    @api.depends('company_id')
    def _compute_closing_opening_journals(self):
        Journal = self.env['account.journal']
        for rec in self:
            if not rec.company_id:
                rec.closing_journal_ids = False
                rec.opening_journal_ids = False
                continue
            base = [('company_id', '=', rec.company_id.id), ('type', '=', 'general')]
            rec.closing_journal_ids = Journal.search(
                base + ['|', ('name', 'ilike', 'cierre'), ('code', '=ilike', 'cier%')]
            )
            rec.opening_journal_ids = Journal.search(
                base + ['|', ('name', 'ilike', 'apertura'), ('code', '=ilike', 'apert%')]
            )

    @api.depends('company_id', 'date_start', 'date_end')
    def _compute_name(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                rec.name = 'Libro Inv. y Balances - %s al %s - %s' % (
                    rec.date_start.strftime('%d/%m/%Y'),
                    rec.date_end.strftime('%d/%m/%Y'),
                    rec.company_id.name or '',
                )
            else:
                rec.name = 'Libro Inventarios y Balances'

    # ------------------------------------------------------------------
    # Generacion de reportes (individual y libro completo)
    # ------------------------------------------------------------------
    def _generate_single(self, nn):
        """Genera Excel + PDF de un formato. Cada formato define
        `_prepare_report_<nn>()` que retorna la instancia del reporte."""
        self.ensure_one()
        self._check_before_generate()
        report = getattr(self, '_prepare_report_%s' % nn)()
        self._store_report(nn, report)
        self._mark_generated()

    def action_generate_all_xls(self):
        """Libro completo en Excel: una hoja por formato (3.1 a 3.20)."""
        self.ensure_one()
        self._check_before_generate()
        xlsx_bytes, xls_name, _pdf_source = self._build_consolidated_xlsx()
        self.write({
            'xls_binary_all': base64.b64encode(xlsx_bytes),
            'xls_filename_all': xls_name,
        })
        self._mark_generated()

    def action_generate_all_pdf(self):
        """Libro completo en PDF (una sola conversion con LibreOffice).
        Tambien actualiza el Excel completo, para que ambos archivos
        correspondan siempre a la misma generacion."""
        self.ensure_one()
        self._check_before_generate()
        xlsx_bytes, xls_name, pdf_source = self._build_consolidated_xlsx(
            with_pdf_source=True,
        )
        pdf_bytes = self._xlsx_to_pdf(pdf_source)
        self.write({
            'xls_binary_all': base64.b64encode(xlsx_bytes),
            'xls_filename_all': xls_name,
            'pdf_binary_all': base64.b64encode(pdf_bytes),
            'pdf_filename_all': xls_name.replace('.xlsx', '.pdf'),
        })
        self._mark_generated()

    def _build_consolidated_xlsx(self, with_pdf_source=False):
        """Arma el XLSX con los 19 formatos y sus hojas de trabajo. Con
        `with_pdf_source` arma ademas, con los mismos datos, un XLSX sin
        hojas de trabajo, que es el que se convierte a PDF. Si algun
        formato falla, se detiene e indica cual.
        Retorna (bytes, nombre de archivo, bytes para PDF o None)."""
        self.ensure_one()

        def guarded(code, title, func):
            try:
                return func()
            except UserError as err:
                raise UserError(_('Formato %s - %s:\n%s') % (
                    code, title, err.args[0] if err.args else err,
                ))
            except Exception as err:
                _logger.exception(
                    'PLE Inv. y Balances: error en el formato %s (libro completo)',
                    code,
                )
                raise UserError(_(
                    'No se pudo generar el formato %s - %s.\n%s'
                ) % (code, title, err))

        reports = [
            (code, title, guarded(
                code, title,
                lambda nn=nn: getattr(self, '_prepare_report_%s' % nn)(),
            ))
            for nn, code, title in FORMATOS
        ]

        def write_workbook(include_extra):
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            for code, title, report in reports:
                guarded(code, title, lambda r=report: r.write_sheet(workbook))
                if include_extra:
                    guarded(code, title, lambda r=report: r.write_extra_sheets(workbook))
            workbook.close()
            return output.getvalue()

        xlsx_bytes = write_workbook(include_extra=True)
        pdf_source = write_workbook(include_extra=False) if with_pdf_source else None

        safe = ''.join(
            c if c.isalnum() else '_' for c in (self.company_id.name or 'company')
        )
        xls_name = 'Libro_Inv_Bal_Completo_%s_%s.xlsx' % (
            safe, self.date_end.strftime('%Y%m'),
        )
        return xlsx_bytes, xls_name, pdf_source

    def action_reset_to_draft(self):
        vals = {
            'state': 'draft', 'date_generated': False,
            'xls_binary_all': False, 'xls_filename_all': False,
            'pdf_binary_all': False, 'pdf_filename_all': False,
        }
        for nn, _code, _title in FORMATOS:
            vals.update({
                'xls_binary_%s' % nn: False,
                'xls_filename_%s' % nn: False,
                'pdf_binary_%s' % nn: False,
                'pdf_filename_%s' % nn: False,
            })
        self.write(vals)

    # ------------------------------------------------------------------
    # Guardado de archivos, validaciones y conversion a PDF
    # ------------------------------------------------------------------
    def _store_report(self, nn, report):
        """Genera Excel + PDF de un reporte y los guarda en sus campos.

        `report` es una instancia de la clase constructora del formato
        (expone get_content() -> bytes xlsx y get_filename() -> str).
        """
        self.ensure_one()
        xlsx_bytes = report.get_content()
        xls_name = report.get_filename()
        # El PDF lleva solo el formato oficial, sin hojas de trabajo.
        pdf_bytes = self._xlsx_to_pdf(report.get_content(include_extra=False))
        pdf_name = xls_name.replace('.xlsx', '.pdf')
        self.write({
            'xls_binary_%s' % nn: base64.b64encode(xlsx_bytes),
            'xls_filename_%s' % nn: xls_name,
            'pdf_binary_%s' % nn: base64.b64encode(pdf_bytes),
            'pdf_filename_%s' % nn: pdf_name,
        })

    def _check_before_generate(self):
        """Validaciones comunes antes de generar cualquier formato 3.x."""
        self.ensure_one()
        self._check_company_access()
        self._check_dates()

    def _check_company_access(self):
        """La compania del registro debe estar activa en el selector de
        companias del usuario (env.companies)."""
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise UserError(_(
                'No es posible generar el reporte para la compañía seleccionada. '
                'Verifique que la compañía esté activa en el selector de compañías.'
            ))

    def _check_dates(self):
        self.ensure_one()
        if not self.date_start or not self.date_end:
            raise UserError(_('Debe indicar la Fecha Inicio y la Fecha Fin del reporte.'))
        if self.date_start > self.date_end:
            raise UserError(_('La Fecha Inicio no puede ser posterior a la Fecha Fin.'))

    def _mark_generated(self):
        self.write({
            'date_generated': fields.Date.context_today(self),
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

    # ==================================================================
    # HELPERS COMPARTIDOS - base para un futuro mixin
    # ==================================================================
    # Los usan varios formatos. No dependen de un formato concreto.

    # Clases de resultados (gestion, naturaleza, saldos intermedios, costos).
    PL_CLASSES = ('6', '7', '8', '9')

    def _is_pl_code(self, code):
        """True si la cuenta es de resultados del periodo (clases 6 a 9),
        excepto la 89 (determinacion del resultado), que solo la mueven los
        asientos de cierre/apertura y va a resultados acumulados."""
        return code[:1] in self.PL_CLASSES and not code.startswith('89')

    def _balances_by_account(self, date_to, account_ids=None):
        """Saldo (debe - haber) por account_id de asientos posteados hasta
        `date_to` inclusive. Si se pasa `account_ids`, filtra por esas
        cuentas. Retorna {account_id: saldo}.

        En Odoo 18 `account.account.code` es company-dependent y no existe
        como columna en account_account, por eso se agrupa por account_id.
        """
        self.ensure_one()
        query = """
            SELECT aml.account_id, COALESCE(SUM(aml.debit - aml.credit), 0.0)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.company_id = %(company)s
              AND am.state = 'posted'
              AND am.date <= %(date_to)s
              AND am.id NOT IN %(excluded)s
        """
        params = {
            'company': self.company_id.id,
            'date_to': date_to,
            'excluded': self._get_excluded_move_ids(),
        }
        if account_ids is not None:
            if not account_ids:
                return {}
            query += " AND aml.account_id IN %(accounts)s"
            params['accounts'] = tuple(account_ids)
        query += " GROUP BY aml.account_id"
        self.env.cr.execute(query, params)
        return {r[0]: float(r[1] or 0.0) for r in self.env.cr.fetchall() if r[0]}

    def _get_excluded_move_ids(self):
        """Asientos de cierre del ejercicio que no se consideran en los
        saldos: los de los diarios de cierre con fecha igual a `date_end`
        (saldos antes del cierre). Tupla no vacia, apta para `NOT IN`."""
        self.ensure_one()
        ids = []
        if self.closing_journal_ids and self.date_end:
            ids = self.env['account.move'].search([
                ('company_id', '=', self.company_id.id),
                ('journal_id', 'in', self.closing_journal_ids.ids),
                ('date', '=', self.date_end),
                ('state', '=', 'posted'),
            ]).ids
        return tuple(ids) or (0,)

    def _get_period_closing_opening_move_ids(self):
        """Asientos de los diarios de cierre o apertura dentro del periodo
        [date_start, date_end]. No son movimientos, flujos ni resultados
        del periodo. Tupla no vacia, apta para `NOT IN`."""
        self.ensure_one()
        journals = self.closing_journal_ids | self.opening_journal_ids
        ids = []
        if journals and self.date_start and self.date_end:
            ids = self.env['account.move'].search([
                ('company_id', '=', self.company_id.id),
                ('journal_id', 'in', journals.ids),
                ('date', '>=', self.date_start),
                ('date', '<=', self.date_end),
                ('state', '=', 'posted'),
            ]).ids
        return tuple(ids) or (0,)

    def _account_balances_as_of(self, date_to=None):
        """Saldo por codigo de cuenta hasta `date_to` (por defecto
        `date_end`). Retorna {codigo: saldo}."""
        self.ensure_one()
        by_id = self._balances_by_account(date_to or self.date_end)
        accounts = self.env['account.account'].with_company(
            self.company_id
        ).browse(list(by_id))
        result = {}
        for account in accounts:
            code = account.code or ''
            if code:
                result[code] = result.get(code, 0.0) + by_id[account.id]
        return result

    def _get_accounts_by_prefix(self, prefixes):
        """Cuentas de la compania cuyo codigo empieza con alguno de los
        prefijos dados, ordenadas por codigo."""
        self.ensure_one()
        domain = expression.AND([
            expression.OR([[('code', '=like', '%s%%' % p)] for p in prefixes]),
            [('company_ids', 'in', self.company_id.id)],
        ])
        accounts = self.env['account.account'].with_company(
            self.company_id
        ).search(domain)
        return accounts.sorted(lambda a: a.code or '')

    def _get_open_items(self, prefixes, date_source='move', split_no_partner=False):
        """Documentos pendientes al `date_end` en las cuentas indicadas.

        El saldo pendiente de cada linea se calcula A LA FECHA DE CORTE:
        saldo de la linea menos las conciliaciones cuya `max_date` sea
        <= date_end. No se consideran los asientos de cierre de la fecha fin
        (ver _get_excluded_move_ids). Una conciliacion solo se descuenta si la linea
        contraria TAMBIEN cuenta: asiento publicado, fecha <= date_end y
        misma familia de cuentas. Asi el total del reporte siempre es igual
        al saldo contable de las cuentas, aunque existan conciliaciones
        contra asientos cancelados (p.ej. aperturas/cierres anulados).

        Agrupa por tercero (partner comercial) y documento (asiento). Las
        lineas sin tercero (p.ej. diferencias de cambio) se agrupan en una
        sola fila "VARIOS", o por asiento si `split_no_partner` es True.

        date_source:
            'invoice' -> fecha de emision del comprobante (invoice_date)
            'move'    -> fecha del asiento (inicio de la operacion)

        Retorna {'lines': [{doc_type, doc_number, name, doc_ref, amount,
        date}], 'total': float}.
        """
        self.ensure_one()
        accounts = self._get_accounts_by_prefix(prefixes)
        if not accounts:
            return {'lines': [], 'total': 0.0}

        self.env.cr.execute("""
            SELECT aml.id,
                   aml.balance
                   - COALESCE((SELECT SUM(p.amount)
                                 FROM account_partial_reconcile p
                                 JOIN account_move_line cl ON cl.id = p.credit_move_id
                                 JOIN account_move cm ON cm.id = cl.move_id
                                WHERE p.debit_move_id = aml.id
                                  AND p.max_date <= %(date_to)s
                                  AND cm.state = 'posted'
                                  AND cm.id NOT IN %(excluded)s
                                  AND cl.date <= %(date_to)s
                                  AND cl.account_id IN %(accounts)s), 0.0)
                   + COALESCE((SELECT SUM(p.amount)
                                 FROM account_partial_reconcile p
                                 JOIN account_move_line dl ON dl.id = p.debit_move_id
                                 JOIN account_move dm ON dm.id = dl.move_id
                                WHERE p.credit_move_id = aml.id
                                  AND p.max_date <= %(date_to)s
                                  AND dm.state = 'posted'
                                  AND dm.id NOT IN %(excluded)s
                                  AND dl.date <= %(date_to)s
                                  AND dl.account_id IN %(accounts)s), 0.0)
                   AS residual
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE am.company_id = %(company)s
               AND am.state = 'posted'
               AND am.id NOT IN %(excluded)s
               AND aml.date <= %(date_to)s
               AND aml.account_id IN %(accounts)s
        """, {
            'date_to': self.date_end,
            'company': self.company_id.id,
            'accounts': tuple(accounts.ids),
            'excluded': self._get_excluded_move_ids(),
        })
        residual_by_line = {
            line_id: float(residual or 0.0)
            for line_id, residual in self.env.cr.fetchall()
            if abs(float(residual or 0.0)) >= 0.005
        }
        if not residual_by_line:
            return {'lines': [], 'total': 0.0}

        groups = {}
        move_lines = self.env['account.move.line'].browse(list(residual_by_line))
        for line in move_lines:
            partner = line.partner_id.commercial_partner_id
            move = line.move_id
            if partner:
                key = (partner.id, move.id)
            elif split_no_partner:
                key = (0, move.id)
            else:
                key = (0, 0)
            if date_source == 'invoice':
                doc_date = move.invoice_date or move.date
            else:
                doc_date = move.date

            group = groups.get(key)
            if group is None:
                group = groups[key] = {
                    'partner': partner,
                    'move': move,
                    'date': doc_date,
                    'amount': 0.0,
                }
            group['amount'] += residual_by_line[line.id]
            if doc_date and (not group['date'] or doc_date < group['date']):
                group['date'] = doc_date

        rows = []
        for key, group in groups.items():
            if abs(group['amount']) < 0.005:
                continue
            partner = group['partner']
            move = group['move']
            if partner:
                id_type = getattr(partner, 'l10n_latam_identification_type_id', False)
                rows.append({
                    'doc_type': (getattr(id_type, 'l10n_pe_vat_code', False) or '0')
                                if id_type else '0',
                    'doc_number': partner.vat or '-',
                    'name': partner.name or '',
                    'doc_ref': move.ref or move.name or '-',
                    'amount': group['amount'],
                    'date': group['date'],
                })
            else:
                split = key != (0, 0)
                rows.append({
                    'doc_type': '0',
                    'doc_number': '-',
                    'name': _('VARIOS (sin tercero asignado)'),
                    'doc_ref': (move.name or '-') if split else '-',
                    'amount': group['amount'],
                    'date': group['date'] if split else self.date_end,
                })

        rows.sort(key=lambda r: ((r['name'] or '').upper(), r['date'] or date.min))
        return {
            'lines': rows,
            'total': sum(r['amount'] for r in rows),
        }

    def _partner_identity(self, partner, empty_label):
        """(tipo doc Tabla 2, numero, nombre) del partner comercial, o una
        fila generica si no hay tercero."""
        if not partner:
            return '0', '-', empty_label
        id_type = getattr(partner, 'l10n_latam_identification_type_id', False)
        doc_type = (getattr(id_type, 'l10n_pe_vat_code', False) or '0') if id_type else '0'
        return doc_type, partner.vat or '-', partner.name or ''

    def _balances_by_account_partner(self, date_to, account_ids):
        """Saldo (debe - haber) por (account_id, partner comercial) hasta
        `date_to`. Retorna {(account_id, partner_id or 0): saldo}."""
        self.ensure_one()
        if not account_ids:
            return {}
        self.env.cr.execute("""
            SELECT aml.account_id,
                   COALESCE(rp.commercial_partner_id, rp.id, 0) AS partner_id,
                   COALESCE(SUM(aml.debit - aml.credit), 0.0)
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
              LEFT JOIN res_partner rp ON rp.id = aml.partner_id
             WHERE am.company_id = %(company)s
               AND am.state = 'posted'
               AND am.id NOT IN %(excluded)s
               AND aml.date <= %(date_to)s
               AND aml.account_id IN %(accounts)s
             GROUP BY aml.account_id, COALESCE(rp.commercial_partner_id, rp.id, 0)
        """, {
            'company': self.company_id.id,
            'date_to': date_to,
            'accounts': tuple(account_ids),
            'excluded': self._get_excluded_move_ids(),
        })
        return {
            (account_id, partner_id or 0): float(balance or 0.0)
            for account_id, partner_id, balance in self.env.cr.fetchall()
        }
