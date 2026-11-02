# -*- coding: utf-8 -*-
import base64
import io
import logging
import os
import subprocess
import tempfile
from calendar import monthrange
from collections import defaultdict
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None
    _logger.warning("xlsxwriter no disponible - PLE 13.1 no podrá generar Excel")


DEFAULT_ESTABLISHMENT_CODE = '0000'

# Tabla 11 SUNAT - Método de valuación
# Odoo cost_method -> código SUNAT
VALUATION_METHOD_MAP = {
    'average': '1',   # Promedio diario/ponderado
    'fifo': '7',      # PEPS
    'standard': '8',  # Otros (Especificar)
}

# Tabla 12 SUNAT - Tipo de operación
OPERATION_TYPE_MAP = {
    'incoming': '02',
    'outgoing': '01',
    'internal': '05',
}

OPENING_BALANCE_OP_CODE = '16'  # SALDO INICIAL


class PleReportStockValuedInventory(models.Model):
    _name = 'ple.report.stock.valued.inventory'
    _description = 'PLE Registro de Inventario Permanente Valorizado 13.1'
    _order = 'period desc'

    name = fields.Char(compute='_compute_name', store=True)
    period = fields.Char(
        string='Período',
        required=True,
        default=lambda self: date.today().strftime('%Y-%m'),
        help='Formato YYYY-MM',
    )
    date_start = fields.Date(compute='_compute_dates', store=True)
    date_end = fields.Date(compute='_compute_dates', store=True)
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        [('draft', 'Borrador'), ('confirmed', 'Confirmado')],
        default='draft',
        required=True,
    )
    file = fields.Binary(string='Archivo', readonly=True)
    filename = fields.Char(readonly=True)

    pdf_file = fields.Binary(string='Archivo PDF', readonly=True)
    pdf_filename = fields.Char(readonly=True)

    @api.depends('period')
    def _compute_name(self):
        for rec in self:
            rec.name = _("Inventario Valorizado 13.1 %s") % (rec.period or '')

    @api.depends('period')
    def _compute_dates(self):
        for rec in self:
            if rec.period and len(rec.period) == 7 and rec.period[4] == '-':
                try:
                    y, m = int(rec.period[:4]), int(rec.period[5:])
                    rec.date_start = date(y, m, 1)
                    rec.date_end = date(y, m, monthrange(y, m)[1])
                    continue
                except (ValueError, TypeError):
                    pass
            rec.date_start = False
            rec.date_end = False

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.state = 'confirmed'

    def action_reset_draft(self):
        self.state = 'draft'

    def action_generate_report(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("Falta instalar la librería xlsxwriter."))
        if not (self.date_start and self.date_end):
            raise UserError(_("Período inválido. Use formato YYYY-MM."))

        xlsx_bytes = self._build_xlsx_bytes()
        self.file = base64.b64encode(xlsx_bytes)
        self.filename = "13_1_%s_%s.xlsx" % (
            (self.company_id.vat or 'SIN_RUC').replace('-', ''),
            self.period.replace('-', ''),
        )

    def action_generate_pdf(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("Falta instalar la librería xlsxwriter."))
        if not (self.date_start and self.date_end):
            raise UserError(_("Período inválido. Use formato YYYY-MM."))

        # Reutiliza el XLSX ya generado; si no existe, lo arma al vuelo.
        if self.file:
            xlsx_bytes = base64.b64decode(self.file)
        else:
            xlsx_bytes = self._build_xlsx_bytes()

        pdf_content = self._xlsx_to_pdf(xlsx_bytes)
        self.pdf_file = base64.b64encode(pdf_content)
        self.pdf_filename = "13_1_%s_%s.pdf" % (
            (self.company_id.vat or 'SIN_RUC').replace('-', ''),
            self.period.replace('-', ''),
        )

    # ------------------------------------------------------------------
    # Generacion XLSX (bytes)
    # ------------------------------------------------------------------
    def _build_xlsx_bytes(self):
        """Arma el workbook y devuelve los bytes del XLSX."""
        products = self._get_products_with_movements()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('13.1')

        # --- Configuracion de impresion (para la conversion a PDF) ---
        # Mono-periodo y 14 columnas: fit_to_pages al ancho. NO se usa
        # repeat_rows porque la cabecera cambia por producto.
        sheet.set_landscape()
        sheet.set_paper(9)                      # 9 = A4
        sheet.set_margins(0.2, 0.2, 0.3, 0.3)   # left, right, top, bottom
        sheet.fit_to_pages(1, 0)                # 14 columnas en una pagina de ancho

        self._write_report(workbook, sheet, products)
        workbook.close()
        data = output.getvalue()
        output.close()
        return data

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
                        "La conversión a PDF excedió el tiempo límite. "
                        "El reporte puede ser demasiado grande."
                    ))

            if result is None:
                raise UserError(
                    _("LibreOffice no está disponible en el servidor.")
                )

            pdf_path = os.path.join(tmp, 'report.pdf')
            if result.returncode != 0 or not os.path.exists(pdf_path):
                err = (result.stderr or b'').decode('utf-8', 'replace')[:500]
                raise UserError(
                    _("No se pudo generar el PDF.\n%s")
                    % (err or 'Error desconocido de LibreOffice.')
                )

            with open(pdf_path, 'rb') as fh:
                return fh.read()

    # ------------------------------------------------------------------
    # Data mining
    # ------------------------------------------------------------------
    def _svl_domain_base(self):
        return [
            ('company_id', '=', self.company_id.id),
            ('stock_move_id.state', '=', 'done'),
        ]

    def _svl_env(self):
        """SVL con la compania forzada en el contexto, para evitar que el
        filtro multicompania devuelva vacio segun el switcher."""
        return self.env['stock.valuation.layer'].with_company(
            self.company_id
        ).with_context(
            allowed_company_ids=[self.company_id.id]
        )

    def _get_products_with_movements(self):
        """Productos almacenables con al menos un SVL en el rango."""
        svls = self._svl_env().search(
            self._svl_domain_base() + [
                ('stock_move_id.date', '>=', self.date_start),
                ('stock_move_id.date', '<=', self.date_end),
            ]
        )
        products = svls.mapped('product_id').filtered(lambda p: p.is_storable)
        return products.sorted('name')

    def _get_opening_balance(self, product):
        """Cantidad y valor acumulados en SVL con fecha < date_start."""
        svls = self._svl_env().search(
            self._svl_domain_base() + [
                ('product_id', '=', product.id),
                ('stock_move_id.date', '<', self.date_start),
            ]
        )
        qty = sum(svls.mapped('quantity'))
        value = sum(svls.mapped('value'))
        return qty, value

    def _get_moves_in_range(self, product):
        """Agrupa SVLs por stock.move y ordena por fecha del move."""
        svls = self._svl_env().search(
            self._svl_domain_base() + [
                ('product_id', '=', product.id),
                ('stock_move_id.date', '>=', self.date_start),
                ('stock_move_id.date', '<=', self.date_end),
            ]
        )
        moves_data = defaultdict(lambda: {'qty': 0.0, 'value': 0.0, 'move': False})
        for svl in svls:
            move = svl.stock_move_id
            if not move:
                continue
            moves_data[move.id]['move'] = move
            moves_data[move.id]['qty'] += svl.quantity
            moves_data[move.id]['value'] += svl.value
        # Filtrar movimientos con qty y value = 0 (ej. cancelaciones netas)
        result = [d for d in moves_data.values() if d['move']]
        return sorted(result, key=lambda d: (d['move'].date, d['move'].id))

    def _get_move_document(self, move):
        """Deriva (tipo_doc, serie, numero) desde account.move vinculado."""
        invoice = False
        if move.sale_line_id and move.sale_line_id.order_id:
            invs = move.sale_line_id.order_id.invoice_ids.filtered(
                lambda m: m.state == 'posted'
            )
            invoice = invs[:1]
        elif move.purchase_line_id and move.purchase_line_id.order_id:
            invs = move.purchase_line_id.order_id.invoice_ids.filtered(
                lambda m: m.state == 'posted'
            )
            invoice = invs[:1]

        if not invoice:
            return '00', '0', '00000000'

        doc_type = '00'
        if invoice.l10n_latam_document_type_id:
            doc_type = invoice.l10n_latam_document_type_id.code or '00'

        serie, numero = '0', '00000000'
        if invoice.name and '-' in invoice.name:
            parts = invoice.name.split('-', 1)
            serie = parts[0]
            num_part = parts[1] if len(parts) > 1 else ''
            if num_part.isdigit():
                numero = '%08d' % int(num_part)
            else:
                numero = num_part or '00000000'
        return doc_type, serie, numero

    def _get_operation_type(self, move):
        if move.picking_type_id and move.picking_type_id.code:
            return OPERATION_TYPE_MAP.get(move.picking_type_id.code, '99')
        return '99'

    def _get_valuation_method(self, product):
        cost_method = product.categ_id.property_cost_method
        return VALUATION_METHOD_MAP.get(cost_method, '1')

    def _get_uom_code(self, product):
        return product.uom_id.name or ''

    def _classify_move(self, qty):
        """Retorna 'in' si qty > 0, 'out' si qty < 0."""
        if qty > 0:
            return 'in'
        if qty < 0:
            return 'out'
        return None

    # ------------------------------------------------------------------
    # Escritura Excel
    # ------------------------------------------------------------------
    def _build_formats(self, workbook):
        return {
            'title': workbook.add_format({'bold': True, 'font_size': 11}),
            'label': workbook.add_format({'bold': True}),
            'value': workbook.add_format({'bg_color': '#DDEBF7'}),
            'hdr': workbook.add_format({
                'bold': True, 'bg_color': '#D9D9D9', 'border': 1,
                'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
            }),
            'hdr_in': workbook.add_format({
                'bold': True, 'bg_color': '#FFF2CC', 'border': 1,
                'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
            }),
            'hdr_out': workbook.add_format({
                'bold': True, 'bg_color': '#E2EFDA', 'border': 1,
                'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
            }),
            'hdr_bal': workbook.add_format({
                'bold': True, 'bg_color': '#FCE4D6', 'border': 1,
                'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
            }),
            'cell': workbook.add_format({'border': 1}),
            'cell_c': workbook.add_format({'border': 1, 'align': 'center'}),
            'num': workbook.add_format({'border': 1, 'num_format': '#,##0.00'}),
            'dt': workbook.add_format({'border': 1, 'num_format': 'dd/mm/yyyy', 'align': 'center'}),
            'total_lbl': workbook.add_format({
                'bold': True, 'bg_color': '#D9D9D9', 'border': 1, 'align': 'right',
            }),
            'total_num': workbook.add_format({
                'bold': True, 'bg_color': '#D9D9D9', 'border': 1, 'num_format': '#,##0.00',
            }),
            'total_blank': workbook.add_format({'bg_color': '#D9D9D9', 'border': 1}),
        }

    def _set_column_widths(self, sheet):
        widths = [
            ('A', 12),  # FECHA
            ('B', 14),  # TIPO T10
            ('C', 10),  # SERIE
            ('D', 12),  # NUMERO
            ('E', 12),  # TIPO OP
            ('F', 11),  # ENT CANT
            ('G', 13),  # ENT C.UNIT
            ('H', 13),  # ENT C.TOTAL
            ('I', 11),  # SAL CANT
            ('J', 13),  # SAL C.UNIT
            ('K', 13),  # SAL C.TOTAL
            ('L', 11),  # SALDO CANT
            ('M', 13),  # SALDO C.UNIT
            ('N', 13),  # SALDO C.TOTAL
        ]
        for col, w in widths:
            sheet.set_column('%s:%s' % (col, col), w)

    def _write_report(self, workbook, sheet, products):
        fmt = self._build_formats(workbook)
        self._set_column_widths(sheet)

        row = 0
        # Cabecera global mensual
        row = self._write_global_header(sheet, row, fmt)

        if not products:
            sheet.write(row, 0, _("Sin movimientos valorizados en el período."), fmt['label'])
            return

        for product in products:
            row = self._write_product_block(sheet, product, row, fmt)
            row += 2  # separador entre productos

    def _write_global_header(self, sheet, row, fmt):
        company = self.company_id
        sheet.write(row, 0, "FORMATO 13.1: \"REGISTRO DE INVENTARIO PERMANENTE VALORIZADO - DETALLE DEL INVENTARIO VALORIZADO\"", fmt['title'])
        row += 2
        sheet.write(row, 0, "PERÍODO:", fmt['label'])
        sheet.write(row, 4, self.period or '', fmt['value'])
        row += 1
        sheet.write(row, 0, "RUC:", fmt['label'])
        sheet.write(row, 4, company.vat or '', fmt['value'])
        row += 1
        sheet.write(row, 0, "APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL:", fmt['label'])
        sheet.write(row, 4, company.partner_id.name or '', fmt['value'])
        row += 1
        sheet.write(row, 0, "ESTABLECIMIENTO (1):", fmt['label'])
        sheet.write(row, 4, DEFAULT_ESTABLISHMENT_CODE, fmt['value'])
        row += 2
        return row

    def _write_product_block(self, sheet, product, row, fmt):
        # Metadatos por producto
        sheet.write(row, 0, "CÓDIGO DE LA EXISTENCIA:", fmt['label'])
        sheet.write(row, 4, product.default_code or str(product.id), fmt['value'])
        row += 1
        sheet.write(row, 0, "TIPO (TABLA 5):", fmt['label'])
        sheet.write(row, 4, '', fmt['value'])  # pendiente definir con cliente
        row += 1
        sheet.write(row, 0, "DESCRIPCIÓN:", fmt['label'])
        sheet.write(row, 4, product.display_name or '', fmt['value'])
        row += 1
        sheet.write(row, 0, "CÓDIGO DE LA UNIDAD DE MEDIDA (TABLA 6):", fmt['label'])
        sheet.write(row, 4, self._get_uom_code(product), fmt['value'])
        row += 1
        sheet.write(row, 0, "MÉTODO DE VALUACIÓN (TABLA 11):", fmt['label'])
        sheet.write(row, 4, self._get_valuation_method(product), fmt['value'])
        row += 2

        # Encabezado de la tabla (3 filas fusionadas)
        row = self._write_table_header(sheet, row, fmt)

        # Fila SALDO INICIAL
        opening_qty, opening_value = self._get_opening_balance(product)
        opening_unit = (opening_value / opening_qty) if opening_qty else 0.0
        row = self._write_opening_row(sheet, row, fmt, opening_qty, opening_unit, opening_value)

        # Movimientos del rango
        running_qty = opening_qty
        running_value = opening_value
        totals = {'in_qty': 0.0, 'in_val': 0.0, 'out_qty': 0.0, 'out_val': 0.0}

        for data in self._get_moves_in_range(product):
            move = data['move']
            qty = data['qty']
            value = data['value']
            direction = self._classify_move(qty)
            if direction is None:
                continue

            doc_type, serie, numero = self._get_move_document(move)
            op_type = self._get_operation_type(move)

            row = self._write_movement_row(
                sheet, row, fmt, move, doc_type, serie, numero, op_type,
                direction, abs(qty), abs(value),
                running_qty_after=running_qty + qty,
                running_val_after=running_value + value,
            )
            running_qty += qty
            running_value += value
            if direction == 'in':
                totals['in_qty'] += abs(qty)
                totals['in_val'] += abs(value)
            else:
                totals['out_qty'] += abs(qty)
                totals['out_val'] += abs(value)

        # Fila TOTALES
        row = self._write_totals_row(sheet, row, fmt, totals)
        return row

    def _write_table_header(self, sheet, row, fmt):
        # Fila superior con grupos (fusionar A-E como bloque de documento)
        sheet.merge_range(row, 0, row + 1, 3, "DOCUMENTO DE TRASLADO, COMPROBANTE DE PAGO,\nDOCUMENTO INTERNO O SIMILAR", fmt['hdr'])
        sheet.merge_range(row, 4, row + 1, 4, "TIPO DE\nOPERACIÓN\n(TABLA 12)", fmt['hdr'])
        sheet.merge_range(row, 5, row, 7, "ENTRADAS", fmt['hdr_in'])
        sheet.merge_range(row, 8, row, 10, "SALIDAS", fmt['hdr_out'])
        sheet.merge_range(row, 11, row, 13, "SALDO FINAL", fmt['hdr_bal'])
        row += 1
        sheet.write(row, 5, "CANTIDAD", fmt['hdr_in'])
        sheet.write(row, 6, "COSTO UNITARIO", fmt['hdr_in'])
        sheet.write(row, 7, "COSTO TOTAL", fmt['hdr_in'])
        sheet.write(row, 8, "CANTIDAD", fmt['hdr_out'])
        sheet.write(row, 9, "COSTO UNITARIO", fmt['hdr_out'])
        sheet.write(row, 10, "COSTO TOTAL", fmt['hdr_out'])
        sheet.write(row, 11, "CANTIDAD", fmt['hdr_bal'])
        sheet.write(row, 12, "COSTO UNITARIO", fmt['hdr_bal'])
        sheet.write(row, 13, "COSTO TOTAL", fmt['hdr_bal'])
        row += 1
        # Subcabecera de columnas del bloque documento
        sheet.write(row, 0, "FECHA", fmt['hdr'])
        sheet.write(row, 1, "TIPO (TABLA 10)", fmt['hdr'])
        sheet.write(row, 2, "SERIE", fmt['hdr'])
        sheet.write(row, 3, "NÚMERO", fmt['hdr'])
        # E ya está fusionada arriba
        row += 1
        return row

    def _write_opening_row(self, sheet, row, fmt, qty, unit, total):
        sheet.write(row, 0, '', fmt['cell'])
        sheet.write(row, 1, '', fmt['cell'])
        sheet.write(row, 2, '', fmt['cell'])
        sheet.write(row, 3, 'SALDO INICIAL', fmt['cell_c'])
        sheet.write(row, 4, OPENING_BALANCE_OP_CODE, fmt['cell_c'])
        # Entradas y salidas en 0
        sheet.write_number(row, 5, 0, fmt['num'])
        sheet.write_number(row, 6, 0, fmt['num'])
        sheet.write_number(row, 7, 0, fmt['num'])
        sheet.write_number(row, 8, 0, fmt['num'])
        sheet.write_number(row, 9, 0, fmt['num'])
        sheet.write_number(row, 10, 0, fmt['num'])
        # Saldo final = saldo inicial valorizado
        sheet.write_number(row, 11, qty, fmt['num'])
        sheet.write_number(row, 12, unit, fmt['num'])
        sheet.write_number(row, 13, total, fmt['num'])
        return row + 1

    def _write_movement_row(self, sheet, row, fmt, move, doc_type, serie, numero,
                            op_type, direction, qty_abs, val_abs,
                            running_qty_after, running_val_after):
        sheet.write_datetime(row, 0, move.date, fmt['dt'])
        sheet.write(row, 1, doc_type, fmt['cell_c'])
        sheet.write(row, 2, serie, fmt['cell_c'])
        sheet.write(row, 3, numero, fmt['cell_c'])
        sheet.write(row, 4, op_type, fmt['cell_c'])

        unit = (val_abs / qty_abs) if qty_abs else 0.0
        if direction == 'in':
            sheet.write_number(row, 5, qty_abs, fmt['num'])
            sheet.write_number(row, 6, unit, fmt['num'])
            sheet.write_number(row, 7, val_abs, fmt['num'])
            sheet.write(row, 8, '', fmt['cell'])
            sheet.write(row, 9, '', fmt['cell'])
            sheet.write(row, 10, '', fmt['cell'])
        else:
            sheet.write(row, 5, '', fmt['cell'])
            sheet.write(row, 6, '', fmt['cell'])
            sheet.write(row, 7, '', fmt['cell'])
            sheet.write_number(row, 8, qty_abs, fmt['num'])
            sheet.write_number(row, 9, unit, fmt['num'])
            sheet.write_number(row, 10, val_abs, fmt['num'])

        # Saldo final running: unitario = valor_acum / cant_acum
        running_unit = (running_val_after / running_qty_after) if running_qty_after else 0.0
        sheet.write_number(row, 11, running_qty_after, fmt['num'])
        sheet.write_number(row, 12, running_unit, fmt['num'])
        sheet.write_number(row, 13, running_val_after, fmt['num'])
        return row + 1

    def _write_totals_row(self, sheet, row, fmt, totals):
        sheet.merge_range(row, 0, row, 4, 'TOTALES', fmt['total_lbl'])
        sheet.write_number(row, 5, totals['in_qty'], fmt['total_num'])
        sheet.write(row, 6, '', fmt['total_blank'])
        sheet.write_number(row, 7, totals['in_val'], fmt['total_num'])
        sheet.write_number(row, 8, totals['out_qty'], fmt['total_num'])
        sheet.write(row, 9, '', fmt['total_blank'])
        sheet.write_number(row, 10, totals['out_val'], fmt['total_num'])
        sheet.write(row, 11, '', fmt['total_blank'])
        sheet.write(row, 12, '', fmt['total_blank'])
        sheet.write(row, 13, '', fmt['total_blank'])
        return row + 1