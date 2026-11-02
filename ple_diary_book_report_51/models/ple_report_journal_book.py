import base64
import os
import subprocess
import tempfile

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from ..reports.report_journal_book import JournalBookReportExcel

INVOICE_TYPES = ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')


class PleReportJournalBook(models.Model):
    _name = 'ple.report.journal.book'
    _description = 'Reporte PLE Libro Diario Formato 5.1'
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
                rec.name = 'Libro Diario 5.1 - %s - %s' % (
                    rec.date_start.strftime('%m/%Y'),
                    rec.company_id.name or '',
                )
            else:
                rec.name = 'Libro Diario 5.1'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_xlsx(self):
        self.ensure_one()
        self._check_dates()

        data = self._get_report_data()
        report = JournalBookReportExcel(self, data)
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
            report = JournalBookReportExcel(self, data)
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
    # Helpers
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
        """Consulta los apuntes contables del periodo y arma la lista de
        filas del reporte. CUO se calcula por asiento; correlativo por linea.
        Ambos usan contador (CL, YYYYMM). CL default = '5'.
        """
        self.ensure_one()
        lang = self.env.user.lang or 'en_US'

        query = """
            SELECT
                am.id                                            AS move_id,
                am.date                                          AS fecha_operacion,
                COALESCE(NULLIF(am.ref, ''),
                         NULLIF(aml.name, ''),
                         am.name)                                AS descripcion,
                COALESCE(NULLIF(j.ple_book_code, ''), '5')       AS cl,
                am.name                                          AS nro_documento,
                COALESCE(acc.code_store ->> %s, '')              AS codigo,
                COALESCE(acc.name ->> %s,
                         acc.name ->> 'en_US', '')               AS denominacion,
                COALESCE(p.vat, '')                              AS anexo,
                aml.debit                                        AS debit,
                aml.credit                                       AS credit
            FROM account_move_line aml
            JOIN account_move     am  ON am.id  = aml.move_id
            JOIN account_journal  j   ON j.id   = am.journal_id
            JOIN account_account  acc ON acc.id = aml.account_id
            LEFT JOIN res_partner p   ON p.id   = aml.partner_id
            WHERE am.company_id = %s
              AND am.state = 'posted'
              AND am.date BETWEEN %s AND %s
            ORDER BY COALESCE(j.ple_book_code, '5'),
                     am.date, am.name, am.id, aml.id
        """
        self.env.cr.execute(
            query,
            (str(self.company_id.id), lang, self.company_id.id,
             self.date_start, self.date_end),
        )
        rows = self.env.cr.dictfetchall()

        # CUO: contador (CL, YYYYMM) a nivel de asiento. Formato "CL-00000001".
        cuo_by_move = {}
        move_counters = {}
        for row in rows:
            mid = row['move_id']
            if mid not in cuo_by_move:
                yyyymm = row['fecha_operacion'].strftime('%Y%m')
                key = (row['cl'], yyyymm)
                move_counters[key] = move_counters.get(key, 0) + 1
                cuo_by_move[mid] = '%s-%08d' % (row['cl'], move_counters[key])

        # Correlativo %04d, contador (CL, YYYYMM) a nivel de linea.
        line_counters = {}
        for row in rows:
            key = (row['cl'], row['fecha_operacion'].strftime('%Y%m'))
            line_counters[key] = line_counters.get(key, 0) + 1
            row['correlativo'] = '%04d' % line_counters[key]
            row['cuo'] = cuo_by_move[row['move_id']]

        return rows
