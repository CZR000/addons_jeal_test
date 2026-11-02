import base64
import logging
import os
import subprocess
import tempfile
from calendar import monthrange
from datetime import date, datetime

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

from ..reports.report_stock_permanent_inventory import (
    StockPermanentInventoryReportExcel, MONTHS_ES,
)

_logger = logging.getLogger(__name__)


# Establecimiento default (SUNAT anexo del RUC). Hardcoded a '0000' por
# ahora; se ajustara al valor real cuando el cliente lo defina.
DEFAULT_ESTABLISHMENT_CODE = '0000'


# Mapeo SUNAT tabla 10 -> abreviatura mostrada en columna TIPO.
SUNAT_DOC_TYPE_MAP = {
    '01': '01',  # Factura
    '02': '02',  # Recibo por honorarios
    '03': '03',  # Boleta de venta
    '04': '04',  # Liquidacion de compra
    '05': '05',  # Boleto aereo
    '07': '07',  # Nota de credito
    '08': '08',  # Nota de debito
    '09': '09',  # Guia de remision
    '12': '12',  # Ticket
    '13': '13',  # Documento bancario
    '14': '14',  # Recibo servicios publicos
}


# Mapeo tabla 12 SUNAT desde el tipo de operacion del picking.
# Ajustar aca si el cliente define otro mapeo.
OPERATION_TYPE_MAP = {
    'incoming': '02',   # Compra
    'outgoing': '01',   # Venta
    'internal': '05',   # Traslado
}
OPERATION_TYPE_INITIAL = '16'   # SALDO INICIAL


class PleReportStockPermanentInventory(models.Model):
    _name = 'ple.report.stock.permanent.inventory'
    _description = 'Reporte PLE Registro Inventario Permanente 12.1'
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
                rec.name = 'Registro Inventario 12.1 - %s - %s' % (
                    rec.date_start.strftime('%m/%Y'),
                    rec.company_id.name or '',
                )
            else:
                rec.name = 'Registro Inventario 12.1'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_xlsx(self):
        self.ensure_one()
        self._check_dates()

        data = self._get_report_data()
        report = StockPermanentInventoryReportExcel(self, data)
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
            report = StockPermanentInventoryReportExcel(self, data)
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
        """Arma la estructura del reporte segmentada por mes y producto.

        Retorna una lista de meses; cada mes tiene una lista de productos
        con su saldo inicial y sus movimientos.
        """
        self.ensure_one()

        months = self._get_months_in_range()
        if not months:
            return []

        # Todos los stock.move done de productos almacenables de la
        # compania hasta date_end. Los pre-cargo una sola vez y los
        # agrupo por producto.
        all_moves = self._get_all_moves_up_to_end()
        moves_by_product = {}
        for m in all_moves:
            moves_by_product.setdefault(m.product_id.id, []).append(m)

        # Productos con al menos un movimiento dentro del rango de fechas
        # (los que solo tienen movimientos historicos se saltan)
        products_in_range = self._get_products_in_range()
        if not products_in_range:
            _logger.warning(
                'PLE Registro Inventario 12.1: no se encontraron productos '
                'con movimientos en el rango para la compania %s',
                self.company_id.name,
            )
            return []

        result = []
        # Saldo running por producto entre meses
        running_by_product = {p.id: 0.0 for p in products_in_range}

        # Calcular saldo inicial (antes de date_start) por producto
        for product in products_in_range:
            balance = 0.0
            for m in moves_by_product.get(product.id, []):
                if self._move_date(m) >= self.date_start:
                    break  # ordenado por fecha, corto aca
                delta = self._move_qty_signed(m, product)
                if delta is not None:
                    balance += delta
            running_by_product[product.id] = balance

        for month_from, month_to, month_label in months:
            month_block = {
                'label': month_label,
                'date_from': month_from,
                'date_to': month_to,
                'products': [],
            }

            for product in products_in_range:
                saldo_ini = running_by_product.get(product.id, 0.0)

                # Movimientos del producto dentro del mes
                product_month_moves = [
                    m for m in moves_by_product.get(product.id, [])
                    if month_from <= self._move_date(m) <= month_to
                    and self._move_qty_signed(m, product) is not None
                ]

                if not product_month_moves:
                    # Saltamos productos sin movimientos en este mes
                    continue

                rows = []
                saldo = saldo_ini
                for m in product_month_moves:
                    entrada, salida = self._move_entry_exit(m, product)
                    saldo = saldo + entrada - salida
                    td, serie, numero = self._compute_doc_info(m)
                    rows.append({
                        'fecha': self._move_date(m),
                        'td': td,
                        'serie': serie,
                        'numero': numero,
                        'op_type': self._compute_operation_type(m),
                        'entrada': entrada,
                        'salida': salida,
                        'saldo': saldo,
                    })

                month_block['products'].append({
                    'product_code': product.default_code or '',
                    'product_name': product.name or '',
                    'existence_type': '',  # Tabla 5 - vacio por definir
                    'uom_code': product.uom_id.name or '',  # Tabla 6
                    'saldo_inicial': saldo_ini,
                    'lines': rows,
                })

                running_by_product[product.id] = saldo

            if month_block['products']:
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

    def _get_all_moves_up_to_end(self):
        """Todos los stock.move done de productos almacenables de la
        compania cuya fecha <= date_end. Ordenados por producto y fecha
        para permitir calculo de saldo inicial + procesamiento por mes."""
        end_dt = datetime.combine(self.date_end, datetime.max.time())
        return self.env['stock.move'].with_company(
            self.company_id
        ).with_context(
            allowed_company_ids=[self.company_id.id]
        ).search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('date', '<=', end_dt),
            ('product_id.is_storable', '=', True),
        ], order='product_id, date, id')

    def _get_products_in_range(self):
        """Productos almacenables con al menos un stock.move done dentro
        del rango de fechas. Ordenados por product.name."""
        start_dt = datetime.combine(self.date_start, datetime.min.time())
        end_dt = datetime.combine(self.date_end, datetime.max.time())
        moves = self.env['stock.move'].with_company(
            self.company_id
        ).with_context(
            allowed_company_ids=[self.company_id.id]
        ).search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('date', '>=', start_dt),
            ('date', '<=', end_dt),
            ('product_id.is_storable', '=', True),
        ])
        products = moves.mapped('product_id')
        return products.sorted(lambda p: (p.name or '').lower())

    def _move_date(self, move):
        """Retorna solo la parte date de stock.move.date (que es Datetime)."""
        d = move.date
        return d.date() if isinstance(d, datetime) else d

    def _move_qty(self, move, product):
        """Cantidad ejecutada del move en la UoM del producto."""
        qty = move.quantity if move.state == 'done' else move.product_uom_qty
        if move.product_uom and product.uom_id and move.product_uom != product.uom_id:
            return move.product_uom._compute_quantity(qty, product.uom_id)
        return qty

    def _move_direction(self, move):
        """Retorna 'in', 'out' o None segun location.usage.

        - dst interno + src NO interno -> 'in'
        - src interno + dst NO interno -> 'out'
        - ambos internos o ambos no internos -> None (se ignora)
        """
        src_int = move.location_id.usage == 'internal'
        dst_int = move.location_dest_id.usage == 'internal'
        if dst_int and not src_int:
            return 'in'
        if src_int and not dst_int:
            return 'out'
        return None

    def _move_qty_signed(self, move, product):
        """Delta con signo para calculo de saldo. None si se ignora."""
        direction = self._move_direction(move)
        if direction is None:
            return None
        qty = self._move_qty(move, product)
        return qty if direction == 'in' else -qty

    def _move_entry_exit(self, move, product):
        """(entrada, salida) para las columnas del reporte."""
        direction = self._move_direction(move)
        qty = self._move_qty(move, product)
        if direction == 'in':
            return (qty, 0.0)
        if direction == 'out':
            return (0.0, qty)
        return (0.0, 0.0)

    def _get_linked_invoice(self, move):
        """Retorna el account.move (factura) vinculado al stock.move via
        sale_line_id o purchase_line_id. Vacio si no hay."""
        Invoice = self.env['account.move']
        if move.sale_line_id:
            invoices = move.sale_line_id.order_id.invoice_ids.filtered(
                lambda i: i.state == 'posted'
                and i.move_type in ('out_invoice', 'out_refund')
            )
            if invoices:
                return invoices[:1]
        if move.purchase_line_id:
            invoices = move.purchase_line_id.order_id.invoice_ids.filtered(
                lambda i: i.state == 'posted'
                and i.move_type in ('in_invoice', 'in_refund')
            )
            if invoices:
                return invoices[:1]
        return Invoice

    def _compute_doc_info(self, move):
        """Retorna (TIPO tabla 10, SERIE, NUMERO) del comprobante ligado
        al stock.move.

        Si hay factura vinculada:
          TIPO = SUNAT_DOC_TYPE_MAP[l10n_latam_document_type.code]
          SERIE / NUMERO = split de account.move.name por '-'
        Si NO hay factura: '00', '0', '00000000'.
        """
        invoice = self._get_linked_invoice(move)
        if not invoice:
            return ('00', '0', '00000000')

        doc_type_id = getattr(invoice, 'l10n_latam_document_type_id', None)
        code = (doc_type_id.code or '') if doc_type_id else ''
        td = SUNAT_DOC_TYPE_MAP.get(code, '00')

        name = invoice.name or ''
        if '-' in name:
            serie, _, numero = name.partition('-')
        else:
            serie, numero = name, ''
        serie = (serie or '').strip() or '0'
        numero = (numero or '').strip()
        # Padding a 8 digitos si es numerico
        if numero.isdigit():
            numero = numero.zfill(8)
        elif not numero:
            numero = '00000000'
        return (td, serie, numero)

    def _compute_operation_type(self, move):
        """Codigo tabla 12 desde el tipo de picking del stock.move."""
        picking_type = move.picking_type_id
        code = picking_type.code if picking_type else ''
        return OPERATION_TYPE_MAP.get(code, '00')
