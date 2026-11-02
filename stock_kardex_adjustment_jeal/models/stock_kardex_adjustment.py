# -*- coding: utf-8 -*-
import base64
import io
import logging
from collections import defaultdict

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, format_amount, format_date, sql

from .kardex_engine import (
    ADJ_COST, ADJ_FX, ADJ_PRICE, ADJ_PROD, ADJ_RETURN, ADJUSTMENT_ROWS,
    GROUP_IN, GROUP_MANUAL, GROUP_OUT, GROUP_PRODUCTION, INVOICE_ADJUSTMENTS,
    REVIEW_NEGATIVE, REVIEW_PRODUCTION, REVIEW_PURCHASE,
    ROLE_CUSTOMER_RETURN, ROLE_IN, ROLE_MO_CONSUME, ROLE_MO_PRODUCE, ROLE_OUT,
    ROLE_REENTRY, ROLE_UB_IN, ROLE_UB_OUT, ROLE_VENDOR_RETURN,
    ROW_ADJ_COST, ROW_ADJ_FX, ROW_ADJ_PRICE, ROW_ADJ_PROD, ROW_LAYER, ROW_MANUAL,
    ROW_OPENING, ZERO, KardexEngine, money, to_decimal,
)

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

# Tabla 12 SUNAT - Tipo de operación, por uso de las ubicaciones
OPERATION_TYPES = {
    ('internal', 'customer'): '01',   # Venta (solo con orden de venta, R12)
    ('supplier', 'internal'): '02',   # Compra
    ('customer', 'internal'): '05',   # Devolución recibida
    ('internal', 'supplier'): '06',   # Devolución entregada
    ('internal', 'production'): '10',  # Salida a producción
    ('production', 'internal'): '19',  # Entrada de producción
    ('internal', 'inventory'): '28',  # Ajuste por diferencia de inventario
    ('inventory', 'internal'): '28',
    ('internal', 'transit'): '11',    # Transferencia entre almacenes
    ('transit', 'internal'): '21',
}
OPERATION_INVENTORY = '28'
OPERATION_ADJUSTMENT = '99'

ROW_KINDS = [
    (ROW_OPENING, 'Saldo inicial'),
    (ROW_LAYER, 'Movimiento'),
    (ROW_MANUAL, 'Manual incluido'),
    (ROW_ADJ_COST, '99 - Ajuste de costo (promedio o costo de origen)'),
    (ROW_ADJ_FX, '99 - Ajuste diferencia de cambio (factura vs recepción)'),
    (ROW_ADJ_PRICE, '99 - Ajuste diferencia de precio (factura vs recepción)'),
    (ROW_ADJ_PROD, '99 - Ajuste de fabricación o desmontaje'),
]
ADJUSTMENT_TYPES = [
    (ADJ_COST, 'Costo promedio'),
    (ADJ_RETURN, 'Devolución o reingreso al costo de origen'),
    (ADJ_FX, 'Diferencia de cambio (factura vs recepción)'),
    (ADJ_PRICE, 'Diferencia de precio (factura vs recepción)'),
    (ADJ_PROD, 'Fabricación o desmontaje'),
]
REVIEW_TYPES = [
    (REVIEW_NEGATIVE, 'Stock negativo'),
    (REVIEW_PURCHASE, 'Compra'),
    (REVIEW_PRODUCTION, 'Producción'),
]
# Documentos de compra que cuentan como facturado (tabla 10)
PURCHASE_DOCUMENTS = ('01', '03', '04', '07', '08')


class StockKardexAdjustment(models.Model):
    _name = 'stock.kardex.adjustment'
    _description = 'Ajuste del kardex valorizado'
    _inherit = ['mail.thread']
    _check_company_auto = True
    _order = 'date_from desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one(
        comodel_name='res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(
        string='Desde', required=True, tracking=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string='Hasta', required=True, tracking=True,
        default=lambda self: fields.Date.context_today(self))
    filter_product_ids = fields.Many2many(
        comodel_name='product.product',
        relation='stock_kardex_adjustment_product_rel',
        column1='adjustment_id', column2='product_id',
        string='Productos', check_company=True)
    filter_category_ids = fields.Many2many(
        comodel_name='product.category',
        relation='stock_kardex_adjustment_category_rel',
        column1='adjustment_id', column2='category_id',
        string='Categorías')

    # Parámetros (punto 6); se copian de la compañía al crear el proceso.
    return_cost_method = fields.Selection(
        selection=[
            ('origin', 'Costo de la salida de origen'),
            ('current', 'Promedio vigente a la fecha de la devolución'),
        ],
        string='Devoluciones de clientes', required=True,
        default=lambda self: self.env.company.kardex_adj_return_cost_method or 'origin')
    fx_threshold = fields.Monetary(
        string='Umbral de tipo de cambio', currency_field='currency_id',
        default=lambda self: self.env.company.kardex_adj_fx_threshold)
    manual_journal_ids = fields.Many2many(
        comodel_name='account.journal',
        relation='stock_kardex_adjustment_manual_journal_rel',
        column1='adjustment_id', column2='journal_id',
        string='Diarios de asientos manuales', check_company=True,
        default=lambda self: self.env.company.kardex_adj_manual_journal_ids)
    manual_move_ids = fields.Many2many(
        comodel_name='account.move',
        relation='stock_kardex_adjustment_manual_move_rel',
        column1='adjustment_id', column2='move_id',
        string='Asientos manuales adicionales', check_company=True,
        domain="[('state', '=', 'posted')]",
        help='Asientos que se incluyen aunque su diario no esté en la lista.')
    excluded_move_ids = fields.Many2many(
        comodel_name='account.move',
        relation='stock_kardex_adjustment_excluded_move_rel',
        column1='adjustment_id', column2='move_id',
        string='Asientos excluidos', check_company=True,
        help='Asientos manuales que no corresponden a movimientos de inventario '
             '(reclasificaciones, provisiones de tránsito, etc.).')
    excluded_account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='stock_kardex_adjustment_excluded_account_rel',
        column1='adjustment_id', column2='account_id',
        string='Cuentas excluidas',
        default=lambda self: self.env.company.kardex_adj_excluded_account_ids)

    state = fields.Selection(
        selection=[
            ('draft', 'Parámetros'),
            ('computed', 'Calculado'),
            ('done', 'Ajustes registrados'),
        ],
        string='Estado', default='draft', required=True, tracking=True)
    computed_at = fields.Datetime(string='Calculado el', readonly=True)
    row_ids = fields.One2many(
        comodel_name='stock.kardex.adjustment.row', inverse_name='adjustment_id',
        string='Kardex', readonly=True)
    adjustment_row_ids = fields.One2many(
        comodel_name='stock.kardex.adjustment.row', inverse_name='adjustment_id',
        string='Detalle de ajustes', readonly=True,
        domain=[('row_type', 'in', ADJUSTMENT_ROWS)])
    review_row_ids = fields.One2many(
        comodel_name='stock.kardex.adjustment.row', inverse_name='adjustment_id',
        string='Líneas para revisar', readonly=True,
        domain=[('review', '!=', False)])
    summary_ids = fields.One2many(
        comodel_name='stock.kardex.adjustment.summary', inverse_name='adjustment_id',
        string='Resumen por producto', readonly=True)
    line_ids = fields.One2many(
        comodel_name='stock.kardex.adjustment.line', inverse_name='run_id',
        string='Ajustes registrados', readonly=True)

    cost_adjust_total = fields.Monetary(
        string='Ajustes de costo promedio (neto)', currency_field='currency_id', readonly=True)
    return_adjust_total = fields.Monetary(
        string='Ajustes de devoluciones y reingresos (neto)', currency_field='currency_id', readonly=True)
    fx_adjust_total = fields.Monetary(
        string='Ajustes de diferencia de cambio (neto)', currency_field='currency_id', readonly=True)
    price_adjust_total = fields.Monetary(
        string='Ajustes de diferencia de precio (neto)', currency_field='currency_id', readonly=True)
    production_adjust_total = fields.Monetary(
        string='Ajustes de fabricación y desmontaje (neto)', currency_field='currency_id', readonly=True)
    review_count = fields.Integer(string='Líneas para revisar', readonly=True)
    sales_cost = fields.Monetary(
        string='Costo de ventas del kardex', currency_field='currency_id', readonly=True,
        help='Salidas con orden de venta menos devoluciones de clientes, con sus ajustes.')
    simulation_ignore_corrections = fields.Boolean(
        string='Simular sin correcciones manuales',
        help='Calcula como si no existieran las capas marcadas como corrección de costo '
             'del kardex (kardex_cost_correction). Solo para comparar: no se puede registrar.')
    simulation_move_ids = fields.Many2many(
        comodel_name='account.move',
        relation='stock_kardex_adjustment_simulation_move_rel',
        column1='adjustment_id', column2='move_id',
        string='Simular sin estos asientos', check_company=True,
        help='Calcula como si no existieran las capas y apuntes de estos asientos '
             '(por ejemplo, correcciones manuales). Solo para comparar: no se puede registrar.')
    is_simulation = fields.Boolean(compute='_compute_is_simulation')
    adjust_count = fields.Integer(string='Líneas de ajuste', readonly=True)
    to_create_count = fields.Integer(string='Por crear', readonly=True)
    to_update_count = fields.Integer(string='Por actualizar', readonly=True)
    to_reverse_count = fields.Integer(string='Por revertir', readonly=True)
    unchanged_count = fields.Integer(string='Sin cambios', readonly=True)
    pending_count = fields.Integer(compute='_compute_pending_count')
    warning_message = fields.Text(string='Observaciones', readonly=True)
    xlsx_file = fields.Binary(string='Excel', readonly=True, attachment=True)
    xlsx_filename = fields.Char(readonly=True)

    @api.depends('simulation_ignore_corrections', 'simulation_move_ids')
    def _compute_is_simulation(self):
        for rec in self:
            rec.is_simulation = bool(rec.simulation_ignore_corrections or rec.simulation_move_ids)

    @api.depends('to_create_count', 'to_update_count', 'to_reverse_count')
    def _compute_pending_count(self):
        for rec in self:
            rec.pending_count = rec.to_create_count + rec.to_update_count + rec.to_reverse_count

    @api.depends('company_id', 'date_from', 'date_to')
    def _compute_name(self):
        for rec in self:
            if rec.date_from and rec.date_to:
                rec.name = _(
                    'Kardex %(company)s %(date_from)s - %(date_to)s',
                    company=rec.company_id.name or '',
                    date_from=format_date(rec.env, rec.date_from),
                    date_to=format_date(rec.env, rec.date_to))
            else:
                rec.name = _('Ajuste de kardex')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError(_('La fecha inicial no puede ser posterior a la final.'))

    @api.onchange('company_id')
    def _onchange_company_id(self):
        company = self.company_id
        self.return_cost_method = company.kardex_adj_return_cost_method or 'origin'
        self.fx_threshold = company.kardex_adj_fx_threshold
        self.manual_journal_ids = company.kardex_adj_manual_journal_ids
        self.excluded_account_ids = company.kardex_adj_excluded_account_ids

    # ------------------------------------------------------------------
    # Lectura de datos
    # ------------------------------------------------------------------
    def _get_products(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('product_id.is_storable', '=', True),
        ]
        if self.filter_product_ids:
            domain.append(('product_id', 'in', self.filter_product_ids.ids))
        if self.filter_category_ids:
            domain.append(('product_id.categ_id', 'child_of', self.filter_category_ids.ids))
        groups = self.env['stock.valuation.layer'].sudo()._read_group(domain, ['product_id'])
        products = self.env['product.product'].browse([g[0].id for g in groups])
        products = products.with_company(self.company_id)
        return products.filtered(lambda p: p.cost_method == 'average' and not p.lot_valuated)

    def _user_tz(self):
        try:
            return pytz.timezone(self.env.user.tz or 'America/Lima')
        except pytz.UnknownTimeZoneError:
            return pytz.UTC

    def _layer_date(self, move_date, create_date, tz):
        if move_date:
            return move_date
        return pytz.UTC.localize(create_date).astimezone(tz).date()

    def _fetch_layers(self, products):
        """Capas de la compañía hasta ``date_to`` con asiento publicado o sin
        asiento (4.1). Las capas de ajuste creadas por este módulo dentro del
        período se dejan fuera porque se vuelven a calcular, igual que las de
        los asientos que se simulan quitar."""
        self.ensure_one()
        self.env['stock.valuation.layer'].flush_model()
        self.env['account.move'].flush_model(['state', 'date', 'name'])
        self.env['stock.kardex.adjustment.line'].flush_model(['adjustment_type'])
        has_correction = sql.column_exists(self.env.cr, 'stock_valuation_layer', 'kardex_cost_correction')
        correction = 'svl.kardex_cost_correction' if has_correction else 'FALSE'
        has_landed = sql.column_exists(self.env.cr, 'stock_valuation_layer', 'stock_landed_cost_id')
        landed = 'svl.stock_landed_cost_id IS NOT NULL' if has_landed else 'FALSE'
        self.env.cr.execute("""
            SELECT svl.id, svl.product_id, svl.quantity, svl.value, svl.create_date,
                   svl.stock_move_id, svl.account_move_id, am.date, am.name,
                   svl.kardex_adjustment_line_id, svl.description,
                   svl.account_move_line_id, pdl.move_id, kl.adjustment_type, %s, %s
              FROM stock_valuation_layer svl
         LEFT JOIN account_move am ON am.id = svl.account_move_id
         LEFT JOIN account_move_line pdl ON pdl.id = svl.account_move_line_id
         LEFT JOIN stock_kardex_adjustment_line kl ON kl.id = svl.kardex_adjustment_line_id
             WHERE svl.company_id = %%s
               AND svl.product_id IN %%s
               AND (am.id IS NULL OR am.state = 'posted')
          ORDER BY svl.id
        """ % (correction, landed), [self.company_id.id, tuple(products.ids) or (0,)])
        rows = self.env.cr.fetchall()
        # El cursor se lee antes de cualquier acceso al ORM (por ejemplo, la
        # zona horaria del usuario), que podría ejecutar otra consulta encima.
        tz = self._user_tz()
        ignored_moves = set(self.simulation_move_ids.ids)
        layers = []
        # Diferencias de precio de Odoo por línea de factura, de cualquier fecha:
        # cuentan como ya registradas al ajustar esa factura (R3)
        price_diff_by_line = defaultdict(lambda: ZERO)
        for (layer_id, product_id, qty, value, create_date, move_id, account_move_id,
             move_date, move_name, adj_line_id, description, invoice_line_id, invoice_id,
             adj_type, is_correction, is_landed) in rows:
            if account_move_id in ignored_moves or (self.simulation_ignore_corrections and is_correction):
                continue
            if invoice_line_id and not adj_line_id:
                price_diff_by_line[invoice_line_id] += money(value)
            date = self._layer_date(move_date, create_date, tz)
            if date > self.date_to:
                continue
            if adj_line_id and date >= self.date_from:
                continue
            layers.append({
                'id': layer_id,
                'product_id': product_id,
                'qty': to_decimal(qty),
                'value': money(value),
                'create_date': create_date,
                'stock_move_id': move_id,
                'account_move_id': account_move_id,
                'account_move_name': move_name,
                'date': date,
                'no_entry': not account_move_id,
                'adj_type': adj_type if adj_line_id else False,
                'price_diff': bool(invoice_line_id) and not adj_line_id,
                'invoice_id': invoice_id if invoice_line_id and not adj_line_id else False,
                'landed': bool(is_landed),
                'description': description,
            })
        return layers, price_diff_by_line

    def _valuation_accounts(self, products):
        return {
            p.id: p.with_company(self.company_id).categ_id.property_stock_valuation_account_id
            for p in products
        }

    def _fetch_manual_lines(self, products, accounts):
        """Apuntes manuales con producto en la cuenta de valoración de su
        categoría y sin capa de valoración (4.2)."""
        self.ensure_one()
        if not (self.manual_journal_ids or self.manual_move_ids):
            return []
        domain = [
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('product_id', 'in', products.ids),
            ('date', '<=', self.date_to),
            ('move_id.stock_valuation_layer_ids', '=', False),
            ('move_id.kardex_adjustment', '=', False),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        source = []
        if self.manual_journal_ids:
            source.append([('journal_id', 'in', self.manual_journal_ids.ids)])
        if self.manual_move_ids:
            source.append([('move_id', 'in', self.manual_move_ids.ids)])
        if len(source) == 2:
            domain += ['|'] + source[0] + source[1]
        else:
            domain += source[0]
        excluded = self.excluded_move_ids | self.simulation_move_ids
        if excluded:
            domain.append(('move_id', 'not in', excluded.ids))
        if self.excluded_account_ids:
            domain.append(('account_id', 'not in', self.excluded_account_ids.ids))
        lines = self.env['account.move.line'].sudo().search(domain, order='date, id')
        return lines.filtered(lambda l: l.account_id == accounts.get(l.product_id.id))

    # ------------------------------------------------------------------
    # Movimientos: papel, orden del día y enlaces
    # ------------------------------------------------------------------
    @staticmethod
    def _move_field(move, name):
        return move[name] if name in move._fields else move.browse()

    def _move_roles(self, stock_moves):
        """Papel de cada movimiento en el kardex y su operación de producción
        (orden de fabricación o desmontaje), para el orden del día (R11) y
        para enlazar devoluciones, reingresos, consumos y fabricados."""
        roles = {}
        for move in stock_moves:
            src, dst = move.location_id.usage, move.location_dest_id.usage
            role = op = None
            if 'production' in (src, dst):
                mo_raw = self._move_field(move, 'raw_material_production_id')
                mo_fin = self._move_field(move, 'production_id')
                unbuild = self._move_field(move, 'unbuild_id') or self._move_field(move, 'consume_unbuild_id')
                if mo_raw and dst == 'production':
                    role, op = ROLE_MO_CONSUME, ('mo', mo_raw.id)
                elif mo_fin and src == 'production':
                    role, op = ROLE_MO_PRODUCE, ('mo', mo_fin.id)
                elif unbuild:
                    role = ROLE_UB_OUT if dst == 'production' else ROLE_UB_IN
                    op = ('ub', unbuild.id)
            if role is None:
                if dst == 'supplier':
                    role = ROLE_VENDOR_RETURN if move.origin_returned_move_id else ROLE_OUT
                elif src == 'supplier':
                    role = ROLE_REENTRY if move.origin_returned_move_id else ROLE_IN
                elif src == 'customer' and move.origin_returned_move_id:
                    role = ROLE_CUSTOMER_RETURN
                elif dst == 'internal' and src != 'internal':
                    role = ROLE_IN
                elif src == 'internal' and dst != 'internal':
                    role = ROLE_OUT
            roles[move.id] = {'role': role, 'op': op}
        # Orden de cada operación de producción: su primer movimiento
        op_order = {}
        for move_id, data in roles.items():
            if data['op']:
                op_order[data['op']] = min(op_order.get(data['op'], move_id), move_id)
        for data in roles.values():
            data['op_order'] = op_order.get(data['op'])
        return roles

    @staticmethod
    def _event_order(layer, role_data):
        """Grupo y desempate dentro del día (R11): entradas, cadena de
        producción en el orden en que se hizo, salidas."""
        role = role_data.get('role') if role_data else None
        if role in (ROLE_MO_CONSUME, ROLE_MO_PRODUCE, ROLE_UB_OUT, ROLE_UB_IN):
            step = 0 if role in (ROLE_MO_CONSUME, ROLE_UB_OUT) else 1
            return GROUP_PRODUCTION, (role_data['op_order'], step, layer['id'])
        if layer['qty'] > 0 or (layer['qty'] == 0 and role not in (ROLE_OUT, ROLE_VENDOR_RETURN)):
            return GROUP_IN, (0, layer['id'])
        return GROUP_OUT, (0, layer['id'])

    def _layer_role(self, layer, role_data):
        role = role_data.get('role') if role_data else None
        if role is None or (role == ROLE_IN and layer['qty'] < 0) or (role == ROLE_OUT and layer['qty'] > 0):
            return ROLE_IN if layer['qty'] >= 0 else ROLE_OUT
        return role

    # ------------------------------------------------------------------
    # Facturas de proveedor (R3 a R6)
    # ------------------------------------------------------------------
    def _is_invoice_document(self, move):
        doc = move.l10n_latam_document_type_id
        return not doc or doc.code in PURCHASE_DOCUMENTS

    def _purchase_invoice_lines(self, pol, pickings):
        """Líneas de facturas y notas de crédito publicadas de la línea de
        compra, más las de la factura enlazada a mano en la orden o en la
        recepción («Factura para tipo de cambio») cuando está en otra orden."""
        lines = pol.invoice_lines.filtered(
            lambda l: l.parent_state == 'posted'
            and l.move_id.move_type in ('in_invoice', 'in_refund')
            and l.display_type == 'product'
            and self._is_invoice_document(l.move_id))
        linked = pickings.kardex_fx_invoice_id | pol.order_id.kardex_fx_invoice_id
        for invoice in linked.filtered(lambda m: m.state == 'posted'):
            candidates = invoice.invoice_line_ids.filtered(
                lambda l: l.product_id == pol.product_id and l.display_type == 'product')
            # En una OC duplicada cada línea de la factura corresponde a una
            # línea gemela de la otra orden (mismo precio y cantidad).
            twins = candidates.filtered(
                lambda l: l.purchase_line_id
                and not float_compare(l.purchase_line_id.price_unit, pol.price_unit, precision_digits=6)
                and not float_compare(l.purchase_line_id.product_qty, pol.product_qty, precision_digits=4))
            lines |= twins or candidates
        return lines

    def _invoiced_quantity(self, line, pol_lines, product):
        """Cantidad que factura la línea. Las notas de crédito y de débito (07,
        08) solo cambian el valor (descuentos, diferencias de precio), aunque
        repitan la cantidad; una nota de crédito resta la cantidad solo si
        anula por completo la factura de la misma compra."""
        invoice = line.move_id
        qty = to_decimal(line.product_uom_id._compute_quantity(line.quantity, product.uom_id))
        code = invoice.l10n_latam_document_type_id.code
        if invoice.move_type == 'in_refund':
            original = pol_lines.filtered(lambda l: l.move_id == invoice.reversed_entry_id)
            if original and not invoice.currency_id.compare_amounts(
                    abs(sum(original.mapped('balance'))), abs(line.balance)):
                return -qty
            return ZERO
        if code == '08':
            return ZERO
        return qty

    def _invoice_events(self, pol_moves, price_diff_by_line):
        """Un evento por línea de factura de cada línea de compra, en la fecha
        contable de la factura (R5)."""
        company_currency = self.company_id.currency_id
        events = []
        for pol, moves in pol_moves.items():
            product = pol.product_id
            order = pol.order_id
            foreign = order.currency_id != company_currency
            po_price = ZERO
            if pol.price_unit:
                po_qty = to_decimal(pol.product_uom._compute_quantity(1.0, product.uom_id)) or to_decimal(1)
                po_price = to_decimal(pol.price_unit) / po_qty
            lines = self._purchase_invoice_lines(pol, moves.picking_id)
            for line in lines:
                invoice = line.move_id
                if invoice.date > self.date_to:
                    continue
                qty = self._invoiced_quantity(line, lines, product)
                doc_number = (invoice.serie_correlative if 'serie_correlative' in invoice._fields else '') \
                    or invoice.ref or invoice.name
                events.append({
                    'kind': 'invoice',
                    'product': product.id,
                    'date': invoice.date,
                    'group': GROUP_IN,
                    'seq': (1, line.id),
                    'pol': pol.id,
                    'invoice_id': invoice.id,
                    'qty': qty,
                    'value': money(line.balance),
                    'amount_currency': to_decimal(line.amount_currency),
                    'price_diff_value': price_diff_by_line.get(line.id, ZERO),
                    'foreign': foreign and line.currency_id != company_currency,
                    'po_price': po_price,
                    'info': {
                        'invoice_id': invoice.id,
                        'invoices': invoice.name,
                        'invoice_doc': doc_number,
                        'po': order.name,
                    },
                })
        return events

    # ------------------------------------------------------------------
    # Presentación
    # ------------------------------------------------------------------
    def _document_info(self, stock_move):
        invoice = self.env['account.move']
        if stock_move.purchase_line_id:
            invoice = stock_move.purchase_line_id.invoice_lines.move_id.filtered(
                lambda m: m.state == 'posted')[:1]
        elif stock_move.sale_line_id:
            invoice = stock_move.sale_line_id.invoice_lines.move_id.filtered(
                lambda m: m.state == 'posted')[:1]
        if not invoice:
            return '09', stock_move.picking_id.name or stock_move.reference or ''
        doc_type = invoice.l10n_latam_document_type_id.code or '00'
        return doc_type, invoice.name or ''

    @classmethod
    def _is_sale(cls, stock_move):
        """Venta (R12): salida a clientes con orden de venta o con el cliente en
        la guía; o la devolución de una venta. Las salidas a clientes sin
        ninguno de los dos (retiros, regularizaciones) son ajustes de
        inventario."""
        if not stock_move:
            return False
        if stock_move.sale_line_id:
            return True
        if stock_move.location_id.usage == 'customer':
            return cls._is_sale(stock_move.origin_returned_move_id)
        return stock_move.location_dest_id.usage == 'customer' and bool(stock_move.picking_id.partner_id)

    def _operation_type(self, stock_move):
        key = (stock_move.location_id.usage, stock_move.location_dest_id.usage)
        operation = OPERATION_TYPES.get(key, OPERATION_ADJUSTMENT)
        if 'customer' in key and not self._is_sale(stock_move) and not stock_move.origin_returned_move_id:
            # Salidas o entradas de clientes sin orden de venta: ajuste de
            # inventario, no venta (R12)
            operation = OPERATION_INVENTORY
        return operation

    def _layer_info(self, layer, stock_move, tz):
        info = {
            'account_move_id': layer['account_move_id'],
            'account_move_name': layer['account_move_name'] or '',
            'create_date': layer['create_date'],
            'layer_id': layer['id'],
            'reference': layer['description'] or '',
        }
        if stock_move:
            doc_type, doc_number = self._document_info(stock_move)
            info.update({
                'reference': stock_move.picking_id.name or stock_move.reference or '',
                'operation_type': self._operation_type(stock_move),
                'doc_type': doc_type,
                'doc_number': doc_number,
                'partner': (stock_move.picking_id.partner_id or stock_move.partner_id).display_name or '',
                'is_sale': self._is_sale(stock_move),
            })
        else:
            info['operation_type'] = OPERATION_ADJUSTMENT
        if layer['no_entry']:
            info['note'] = _('Capa sin asiento: fecha de creación')
        return info

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------
    def _production_specs(self, layers, moves_by_id, roles):
        """Capas fabricadas de cada orden (R8) y componentes de cada desmontaje
        de una orden (R9)."""
        finished = defaultdict(dict)
        unbuild_in = defaultdict(lambda: defaultdict(dict))
        for layer in layers:
            data = roles.get(layer['stock_move_id']) or {}
            if data.get('role') == ROLE_MO_PRODUCE and layer['qty'] > 0:
                finished[data['op']][layer['id']] = (
                    layer['product_id'], layer['stock_move_id'], layer['value'], {
                        'account_move_id': layer['account_move_id'],
                        'account_move_name': layer['account_move_name'] or '',
                        'layer_id': layer['id'],
                        'reference': moves_by_id[layer['stock_move_id']].reference or '',
                        'operation_type': OPERATION_ADJUSTMENT,
                    })
            elif data.get('role') == ROLE_UB_IN and layer['qty'] > 0:
                unbuild_in[data['op']][layer['product_id']][layer['id']] = (layer['qty'], layer['value'])
        components = {}
        for op, by_product in unbuild_in.items():
            unbuild = self.env['mrp.unbuild'].sudo().browse(op[1])
            if not unbuild.mo_id:
                continue
            raw_moves = unbuild.mo_id.move_raw_ids.filtered(lambda m: m.state == 'done')
            components[op] = [{
                'layers': {lid: qty for lid, (qty, _value) in data.items()},
                'qty': sum(qty for qty, _value in data.values()),
                'raw_moves': raw_moves.filtered(lambda m, p=product_id: m.product_id.id == p).ids,
                'odoo_value': sum(value for _qty, value in data.values()),
            } for product_id, data in by_product.items()]
        return finished, components

    def _production_checks(self, layers, moves_by_id, roles):
        """Consumos de órdenes del período sin capa de valoración completa (R9)."""
        ops = {roles[l['stock_move_id']]['op'] for l in layers
               if l['date'] >= self.date_from and l['stock_move_id']
               and (roles.get(l['stock_move_id']) or {}).get('op')}
        warnings = []
        for kind, res_id in sorted(op for op in ops if op):
            if kind == 'mo':
                record = self.env['mrp.production'].sudo().browse(res_id)
                moves = record.move_raw_ids.filtered(lambda m: m.state == 'done')
            else:
                record = self.env['mrp.unbuild'].sudo().browse(res_id)
                moves = self.env['stock.move'].sudo().search([
                    '|', ('unbuild_id', '=', res_id), ('consume_unbuild_id', '=', res_id),
                    ('state', '=', 'done')])
            for move in moves:
                valued = -sum(move.stock_valuation_layer_ids.mapped('quantity')) if kind == 'mo' \
                    else abs(sum(move.stock_valuation_layer_ids.mapped('quantity')))
                qty = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id)
                if float_compare(valued, qty, precision_rounding=move.product_id.uom_id.rounding) < 0:
                    warnings.append(_(
                        '%(op)s: %(product)s %(qty)s sin capa de valoración (valorizado %(valued)s)',
                        op=record.name, product=move.product_id.display_name,
                        qty=round(qty - valued, 4), valued=round(valued, 4)))
        return warnings

    def _compute_kardex(self):
        """Arma los eventos de todos los productos y ejecuta el motor."""
        self.ensure_one()
        products = self._get_products()
        accounts = self._valuation_accounts(products)
        layers, price_diff_by_line = self._fetch_layers(products)
        tz = self._user_tz()
        stock_moves = self.env['stock.move'].sudo().browse(
            list({l['stock_move_id'] for l in layers if l['stock_move_id']}))
        moves_by_id = {m.id: m for m in stock_moves}
        roles = self._move_roles(stock_moves)
        finished, components = self._production_specs(layers, moves_by_id, roles)

        events = []
        pol_moves = defaultdict(lambda: self.env['stock.move'].sudo())
        for layer in layers:
            in_period = layer['date'] >= self.date_from
            stock_move = moves_by_id.get(layer['stock_move_id'])
            role_data = roles.get(layer['stock_move_id'])
            role = self._layer_role(layer, role_data)
            group, seq = self._event_order(layer, role_data)
            event = {
                'kind': 'layer',
                'product': layer['product_id'],
                'date': layer['date'],
                'group': group,
                'seq': seq,
                'layer_id': layer['id'],
                'qty': layer['qty'],
                'value': layer['value'],
                'stock_move_id': layer['stock_move_id'],
                'role': role,
                'price_diff': layer['price_diff'],
                'adj_type': layer['adj_type'],
            }
            if layer['invoice_id']:
                event['price_diff_invoice_id'] = layer['invoice_id']
            if layer['landed']:
                event['landed'] = True
            if stock_move:
                if stock_move.origin_returned_move_id:
                    event['origin_move_id'] = stock_move.origin_returned_move_id.id
                    event['origin_origin_move_id'] = stock_move.origin_returned_move_id.origin_returned_move_id.id
                if stock_move.purchase_line_id and role in (ROLE_IN, ROLE_REENTRY, ROLE_VENDOR_RETURN):
                    event['pol'] = stock_move.purchase_line_id.id
                    pol_moves[stock_move.purchase_line_id] |= stock_move
                op = role_data and role_data.get('op')
                if role in (ROLE_MO_CONSUME, ROLE_MO_PRODUCE):
                    event['mo_finished'] = finished.get(op, {})
                elif role == ROLE_UB_OUT and op in components:
                    event['ub_components'] = components[op]
            if in_period or event.get('pol'):
                # Las recepciones anteriores al período también: los ajustes de
                # sus facturas del período van debajo de ellas
                info = self._layer_info(layer, stock_move, tz)
                event['info'] = info
                event['note'] = info.get('note', '') if in_period else ''
            events.append(event)

        events += self._invoice_events(pol_moves, price_diff_by_line)

        manual_lines = self._fetch_manual_lines(products, accounts)
        warnings = [_(
            'Leídos: %(products)s productos, %(layers)s capas hasta el cierre '
            '(%(period)s en el período) y %(manual)s apuntes manuales.',
            products=len(products), layers=len(layers),
            period=len([l for l in layers if l['date'] >= self.date_from]),
            manual=len(manual_lines))]
        if self.is_simulation:
            warnings.insert(0, _('SIMULACIÓN: se calculó sin las correcciones indicadas; no se puede registrar.'))
        for aml in manual_lines:
            events.append({
                'kind': 'manual',
                'product': aml.product_id.id,
                'date': aml.date,
                'group': GROUP_MANUAL,
                'seq': (0, aml.id),
                'qty': ZERO,
                'value': money(aml.balance),
                'info': {
                    'account_move_id': aml.move_id.id,
                    'account_move_name': aml.move_id.name,
                    'reference': aml.move_id.ref or aml.name or '',
                    'operation_type': OPERATION_ADJUSTMENT,
                    'doc_type': '00',
                    'doc_number': aml.move_id.name,
                    'partner': aml.partner_id.display_name or '',
                    'create_date': aml.create_date,
                    'aml_id': aml.id,
                    'note': _('Asiento manual incluido (%s)', aml.journal_id.code),
                },
            })

        engine = KardexEngine(
            self.date_from, self.date_to,
            return_cost_method=self.return_cost_method,
            fx_threshold=self.fx_threshold)
        output = engine.run_all(events)
        results = {}
        for product in products:
            result = output['products'].get(product.id)
            if not result:
                continue
            has_activity = any(r['kind'] != ROW_OPENING for r in result['rows'])
            if not has_activity and not result['opening_qty'] and not result['opening_value']:
                continue
            result['product'] = product
            result['account'] = accounts.get(product.id)
            results[product.id] = result
        warnings += self._review_warnings(output['warnings'], products)
        warnings += self._production_checks(layers, moves_by_id, roles)
        return results, warnings

    def _review_warnings(self, reviews, products):
        if not reviews:
            return []
        names = {p.id: p.default_code or p.display_name for p in products}
        labels = dict(REVIEW_TYPES)
        lines = []
        for review in reviews[:60]:
            info = review['info']
            lines.append('- %s %s %s: %s' % (
                format_date(self.env, review['date']), names.get(review['product'], ''),
                info.get('invoices') or info.get('reference') or '', review['text']))
        counts = defaultdict(int)
        for review in reviews:
            counts[labels.get(review['type'], review['type'])] += 1
        header = _('Para revisar: %s', ', '.join('%s %s' % (n, k) for k, n in sorted(counts.items())))
        if len(reviews) > 60:
            lines.append(_('… y %s más.', len(reviews) - 60))
        return [header] + lines

    @staticmethod
    def _adj_key(layer_id, adj_type, invoice_id, date):
        return (layer_id, adj_type, invoice_id or False, date)

    def _planned_adjustments(self, results):
        """Ajustes calculados agrupados por clave de registro: capa ajustada,
        tipo, factura y fecha."""
        planned = {}
        for result in results.values():
            for adj in result['adjustments']:
                key = self._adj_key(adj['layer_id'], adj['type'], adj.get('invoice_id'), adj['date'])
                if key in planned:
                    planned[key] = dict(planned[key], amount=planned[key]['amount'] + adj['amount'])
                else:
                    planned[key] = dict(adj)
        return {key: adj for key, adj in planned.items() if adj['amount']}

    def _layer_counterparts(self, layers):
        """Contrapartida de los ajustes de costo de cada capa (R7): la cuenta
        del asiento del movimiento ajustado; en ventas a clientes con orden de
        venta (y sus devoluciones), la cuenta de costo de ventas de ajustes."""
        cogs = self.company_id.kardex_adj_cogs_account_id
        result = {}
        cache = {}
        for layer in layers:
            move = layer.stock_move_id
            if not move or self._is_sale(move):
                result[layer.id] = cogs
                continue
            if move.id not in cache:
                product = move.product_id.with_company(self.company_id)
                valuation = product.categ_id.property_stock_valuation_account_id
                entry = move.stock_valuation_layer_ids.filtered(
                    lambda l: l.quantity and l.account_move_id and not l.kardex_adjustment_line_id
                )[:1].account_move_id
                lines = entry.line_ids.filtered(lambda l: l.account_id != valuation and l.balance)
                cache[move.id] = max(lines, key=lambda l: abs(l.balance)).account_id if lines else cogs
            result[layer.id] = cache[move.id]
        return result

    def _existing_lines(self, products):
        return self.env['stock.kardex.adjustment.line'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('product_id', 'in', products.ids),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])

    def _plan_sync(self, results):
        """Compara los ajustes calculados con los registrados (5.4): un ajuste
        se actualiza si cambia su importe o su contrapartida."""
        products = self.env['product.product'].browse(list(results))
        planned = self._planned_adjustments(results)
        layers = self.env['stock.valuation.layer'].sudo().browse(list({k[0] for k in planned}))
        counterparts = self._layer_counterparts(layers)
        cogs = self.company_id.kardex_adj_cogs_account_id
        for key, adj in planned.items():
            adj['counterpart'] = cogs if adj['type'] in INVOICE_ADJUSTMENTS else counterparts.get(key[0], cogs)
        existing = {
            self._adj_key(line.adjusted_layer_id.id, line.adjustment_type, line.invoice_id.id, line.date): line
            for line in self._existing_lines(products)
        }
        currency = self.company_id.currency_id
        to_create, to_update, unchanged = [], [], []
        for key, adj in planned.items():
            line = existing.get(key)
            if not line:
                to_create.append(adj)
            elif currency.compare_amounts(line.amount, float(adj['amount'])) != 0 \
                    or (line.counterpart_account_id or cogs) != adj['counterpart']:
                to_update.append((line, adj))
            else:
                unchanged.append(line)
        to_reverse = [line for key, line in existing.items() if key not in planned]
        return to_create, to_update, to_reverse, unchanged

    def action_compute(self):
        for rec in self:
            rec._do_compute()
        return True

    def _do_compute(self):
        self.ensure_one()
        results, warnings = self._compute_kardex()
        to_create, to_update, to_reverse, unchanged = self._plan_sync(results)
        status = {}
        registered = {}
        counterparts = {}
        for adj in to_create + [adj for _line, adj in to_update]:
            counterparts[self._adj_key(adj['layer_id'], adj['type'], adj.get('invoice_id'), adj['date'])] = adj['counterpart']
        for adj in to_create:
            status[self._adj_key(adj['layer_id'], adj['type'], adj.get('invoice_id'), adj['date'])] = 'new'
        for line, adj in to_update:
            key = self._adj_key(adj['layer_id'], adj['type'], adj.get('invoice_id'), adj['date'])
            status[key] = 'changed'
            registered[key] = line
        for line in unchanged:
            key = self._adj_key(line.adjusted_layer_id.id, line.adjustment_type, line.invoice_id.id, line.date)
            status[key] = 'unchanged'
            registered[key] = line
            counterparts[key] = line.counterpart_account_id or self.company_id.kardex_adj_cogs_account_id
        self.row_ids.unlink()
        self.summary_ids.unlink()
        totals = self._store_rows(results, status, registered, counterparts)
        locked = self._locked_dates(to_create, to_update, to_reverse)
        if locked:
            warnings.append(_(
                'Hay ajustes pendientes en fechas cerradas; no se podrán registrar:\n%s',
                '\n'.join(locked)))
        warnings.append(self._sales_cost_check(totals['sales_cost']))
        pending = to_create or to_update or to_reverse
        self.write({
            'state': 'computed' if pending else 'done',
            'computed_at': fields.Datetime.now(),
            'cost_adjust_total': float(totals[ADJ_COST]),
            'return_adjust_total': float(totals[ADJ_RETURN]),
            'fx_adjust_total': float(totals[ADJ_FX]),
            'price_adjust_total': float(totals[ADJ_PRICE]),
            'production_adjust_total': float(totals[ADJ_PROD]),
            'adjust_count': totals['count'],
            'review_count': totals['review'],
            'sales_cost': float(totals['sales_cost']),
            'to_create_count': len(to_create),
            'to_update_count': len(to_update),
            'to_reverse_count': len(to_reverse),
            'unchanged_count': len(unchanged),
            'warning_message': '\n'.join(warnings) or False,
            'xlsx_file': False,
            'xlsx_filename': False,
        })
        return results

    def _sales_cost_check(self, sales_cost):
        """Costo de ventas del kardex contra la cuenta de costo de ventas en
        los asientos de inventario y de ajustes del kardex del período (R7, R12)."""
        cogs = self.company_id.kardex_adj_cogs_account_id
        if not cogs:
            return ''
        self.env['account.move.line'].flush_model()
        self.env.cr.execute("""
            SELECT COALESCE(SUM(aml.balance), 0)
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE aml.company_id = %s AND aml.account_id = %s AND am.state = 'posted'
               AND aml.date BETWEEN %s AND %s
               AND (am.kardex_adjustment OR EXISTS (
                    SELECT 1 FROM stock_valuation_layer svl WHERE svl.account_move_id = am.id))
        """, [self.company_id.id, cogs.id, self.date_from, self.date_to])
        accounting = self.env.cr.fetchone()[0]
        currency = self.company_id.currency_id
        return _(
            'Costo de ventas del kardex (salidas con orden de venta - devoluciones de clientes, '
            'con ajustes): %(kardex)s. Cuenta %(account)s en asientos de inventario y de ajustes '
            'registrados: %(accounting)s.',
            kardex=format_amount(self.env, float(sales_cost), currency),
            account=cogs.code, accounting=format_amount(self.env, accounting, currency))

    def _store_rows(self, results, status, registered=None, counterparts=None):
        registered = registered or {}
        counterparts = counterparts or {}
        Row = self.env['stock.kardex.adjustment.row']
        Summary = self.env['stock.kardex.adjustment.summary']
        row_vals = []
        summary_vals = []
        sequence = 0
        grand = defaultdict(lambda: ZERO)
        grand['count'] = grand['review'] = 0
        for result in sorted(results.values(), key=lambda r: (
                r['account'].code or '', r['product'].default_code or '', r['product'].id)):
            product = result['product']
            totals = defaultdict(lambda: ZERO)
            sale_layers = set()
            for row in result['rows']:
                sequence += 1
                event = row.get('event') or {}
                info = event.get('info') or {}
                kind = row['kind']
                is_adjustment = kind in ADJUSTMENT_ROWS
                layer_id = event.get('layer_id', event.get('seq'))
                vals = {
                    'adjustment_id': self.id,
                    'sequence': sequence,
                    'product_id': product.id,
                    'account_id': result['account'].id,
                    'row_type': kind,
                    'date': row['date'],
                    'account_move_id': info.get('account_move_id') or False,
                    'layer_id': layer_id if kind == ROW_LAYER else False,
                    'adjusted_layer_id': layer_id if is_adjustment else False,
                    'reference': info.get('reference') or '',
                    'operation_type': OPERATION_ADJUSTMENT if is_adjustment else info.get('operation_type') or '',
                    'doc_type': info.get('doc_type') or '',
                    'doc_number': info.get('doc_number') or '',
                    'partner': info.get('partner') or '',
                    'in_qty': float(row.get('in_qty', ZERO)),
                    'in_value': float(row.get('in_value', ZERO)),
                    'out_qty': float(row.get('out_qty', ZERO)),
                    'out_value': float(row.get('out_value', ZERO)),
                    'bal_qty': float(row['bal_qty']),
                    'bal_value': float(row['bal_value']),
                    'raw_bal_value': float(row['raw_bal_value']),
                    'recalc_value': float(row['recalc']) if row.get('recalc') is not None else 0.0,
                    'adjust_value': float(row.get('adjust') or ZERO),
                    'odoo_create_date': info.get('create_date') if kind in (ROW_LAYER, ROW_MANUAL) else False,
                    'note': row.get('note') or (info.get('note') if kind == ROW_MANUAL else '') or '',
                    'tc_invoice': float(row['tc_invoice']) if row.get('tc_invoice') else 0.0,
                    'tc_receipt': float(row['tc_receipt']) if row.get('tc_receipt') else 0.0,
                    'review': row.get('review') or False,
                }
                if is_adjustment:
                    adj_type = row.get('adj_type')
                    key = self._adj_key(layer_id, adj_type, row.get('invoice_id'), row['date'])
                    vals.update({
                        'adj_type': adj_type,
                        'invoice_id': row.get('invoice_id') or False,
                        # Sin estado: se compensa con otra línea de la misma clave
                        'sync_state': status.get(key, False),
                        'adj_move_id': registered[key].move_id.id if key in registered else False,
                        'counterpart_account_id': counterparts[key].id if counterparts.get(key) else False,
                    })
                    if row.get('invoice_id'):
                        vals['note'] = _('%(note)s: factura %(inv)s (%(po)s)', note=row.get('note') or '',
                                         inv=info.get('invoice_doc') or info.get('invoices') or '',
                                         po=info.get('po') or '')
                    totals[adj_type] += row['adjust']
                    grand[adj_type] += row['adjust']
                    grand['count'] += 1
                    if layer_id in sale_layers:
                        totals['sales_cost'] -= row['adjust']
                if vals['review']:
                    grand['review'] += 1
                row_vals.append(vals)
                if kind == ROW_LAYER:
                    totals['in_qty'] += row['in_qty']
                    totals['in_value'] += row['in_value']
                    totals['out_qty'] += row['out_qty']
                    totals['out_value'] += row['out_value']
                    if row.get('recalc') is not None and row['out_qty']:
                        totals['out_recalc'] += row['recalc']
                    elif row['out_qty']:
                        totals['out_recalc'] += row['out_value']
                    if info.get('is_sale'):
                        sale_layers.add(layer_id)
                        totals['sales_cost'] += row['out_value'] - row['in_value']
                elif kind == ROW_MANUAL:
                    totals['manual'] += row['in_value'] - row['out_value']
            grand['sales_cost'] += totals['sales_cost']
            closing_qty = result['closing_qty']
            summary_vals.append({
                'adjustment_id': self.id,
                'product_id': product.id,
                'account_id': result['account'].id,
                'opening_qty': float(result['opening_qty']),
                'opening_value': float(result['opening_value']),
                'in_qty': float(totals['in_qty']),
                'in_value': float(totals['in_value']),
                'out_qty': float(totals['out_qty']),
                'out_value': float(totals['out_value']),
                'out_recalc_value': float(totals['out_recalc']),
                'cost_adjust': float(totals[ADJ_COST]),
                'return_adjust': float(totals[ADJ_RETURN]),
                'fx_adjust': float(totals[ADJ_FX]),
                'price_adjust': float(totals[ADJ_PRICE]),
                'production_adjust': float(totals[ADJ_PROD]),
                'manual_value': float(totals['manual']),
                'sales_cost': float(totals['sales_cost']),
                'closing_qty': float(closing_qty),
                'closing_value': float(result['closing_value']),
                'raw_closing_value': float(result['raw_closing_value']),
                'closing_unit': float(result['closing_value'] / closing_qty) if closing_qty else 0.0,
            })
        Row.create(row_vals)
        Summary.create(summary_vals)
        return grand

    def _locked_dates(self, to_create, to_update, to_reverse):
        """Ajustes pendientes que caen en fechas bloqueadas (5.3)."""
        journal = self.company_id.kardex_adj_journal_id
        dates = defaultdict(int)
        for adj in to_create:
            dates[adj['date']] += 1
        for line, _adj in to_update:
            dates[line.date] += 1
        for line in to_reverse:
            dates[line.date] += 1
        locked = []
        for date in sorted(dates):
            if self.company_id._get_violated_lock_dates(date, False, journal):
                locked.append(_('%(date)s: %(count)s ajuste(s)',
                                date=format_date(self.env, date), count=dates[date]))
        return locked

    # ------------------------------------------------------------------
    # Registro de ajustes (punto 5)
    # ------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        company = self.company_id
        if self.is_simulation:
            raise UserError(_(
                'Es una simulación (sin correcciones manuales): solo sirve para comparar. '
                'Quite las opciones de simulación para registrar.'))
        if not company.kardex_adj_cogs_account_id:
            raise UserError(_(
                'Configure la cuenta de costo de ventas de ajustes de kardex en '
                'Inventario > Configuración > Ajustes.'))
        results = self._do_compute()
        to_create, to_update, to_reverse, _unchanged = self._plan_sync(results)
        locked = self._locked_dates(to_create, to_update, to_reverse)
        if locked:
            raise UserError(_(
                'El período tiene fechas cerradas; no se generó ningún ajuste. '
                'Pendientes:\n%s', '\n'.join(locked)))
        Line = self.env['stock.kardex.adjustment.line'].sudo()
        layers = self.env['stock.valuation.layer'].sudo().browse(
            [adj['layer_id'] for adj in to_create])
        layers_by_id = {l.id: l for l in layers}
        delta_by_product = defaultdict(float)
        items = []
        for adj in to_create:
            layer = layers_by_id[adj['layer_id']]
            items.append({
                'layer': layer,
                'type': adj['type'],
                'amount': float(adj['amount']),
                'date': adj['date'],
                'invoice_id': adj.get('invoice_id') or False,
                'counterpart': adj['counterpart'],
            })
            delta_by_product[layer.product_id] += float(adj['amount'])
        Line._create_adjustments(company, items, run=self)
        amounts = {}
        for line, adj in to_update:
            delta_by_product[line.product_id] += float(adj['amount']) - line.amount
            amounts[line] = float(adj['amount'])
            if line.counterpart_account_id != adj['counterpart']:
                line.counterpart_account_id = adj['counterpart']
        Line._update_amounts(amounts, run=self)
        for line in to_reverse:
            delta_by_product[line.product_id] -= line.amount
        Line.browse([line.id for line in to_reverse])._reverse(run=self)
        if company.kardex_adj_create_layers:
            self._apply_product_costs(delta_by_product)
        self._do_compute()
        self.state = 'done'
        self.message_post(body=_(
            'Ajustes registrados: %(new)s nuevos, %(upd)s actualizados, %(rev)s revertidos.',
            new=len(to_create), upd=len(to_update), rev=len(to_reverse)))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Ajustes de kardex registrados'),
                'message': _('%(new)s nuevos, %(upd)s actualizados, %(rev)s revertidos.',
                             new=len(to_create), upd=len(to_update), rev=len(to_reverse)),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _apply_product_costs(self, delta_by_product):
        """Deja el costo del producto (AVCO) igual al valor / cantidad de sus
        capas y reparte el valor añadido en las capas con saldo, como hace la
        revaluación nativa (5.1)."""
        currency = self.company_id.currency_id
        price_digits = self.env['decimal.precision'].precision_get('Product Price')
        Layer = self.env['stock.valuation.layer'].sudo()
        for product, delta in delta_by_product.items():
            product = product.with_company(self.company_id)
            remaining = Layer.search([
                ('product_id', '=', product.id),
                ('company_id', '=', self.company_id.id),
                ('remaining_qty', '>', 0),
            ])
            remaining_qty = sum(remaining.mapped('remaining_qty'))
            if remaining and remaining_qty and not currency.is_zero(delta):
                left = delta
                for layer in remaining:
                    if layer == remaining[-1]:
                        taken = left
                    else:
                        taken = currency.round(delta * layer.remaining_qty / remaining_qty)
                    layer.remaining_value += taken
                    left -= taken
            groups = Layer._read_group(
                [('product_id', '=', product.id), ('company_id', '=', self.company_id.id)],
                aggregates=['quantity:sum', 'value:sum'])
            qty, value = groups[0] if groups else (0.0, 0.0)
            if qty > 0:
                product.with_context(disable_auto_svl=True).standard_price = round(value / qty, price_digits)

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------
    def action_reset_draft(self):
        self.write(dict(self._ple_clear_vals(), state='draft'))

    def action_view_lines(self):
        self.ensure_one()
        products = self.summary_ids.product_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ajustes registrados'),
            'res_model': 'stock.kardex.adjustment.line',
            'view_mode': 'list,form',
            'domain': [
                ('company_id', '=', self.company_id.id),
                ('product_id', 'in', products.ids),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
            ],
            'context': {'search_default_posted': 1},
        }

    def action_view_rows(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'stock.kardex.adjustment.row',
            'view_mode': 'list',
            'domain': [('adjustment_id', '=', self.id)],
            'context': {'search_default_group_product': 1},
        }

    # ------------------------------------------------------------------
    # Excel (punto 7)
    # ------------------------------------------------------------------
    def action_export_xlsx(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_('Falta la librería xlsxwriter en el servidor.'))
        if self.state == 'draft' or not self.row_ids:
            self._do_compute()
        from .kardex_xlsx import build_workbook
        output = io.BytesIO()
        build_workbook(self, output)
        filename = 'Kardex_%s_%s_%s.xlsx' % (
            (self.company_id.name or '').replace(' ', '_'),
            self.date_from.strftime('%Y%m%d'), self.date_to.strftime('%Y%m%d'))
        self.write({
            'xlsx_file': base64.b64encode(output.getvalue()),
            'xlsx_filename': filename,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/xlsx_file/%s?download=true' % (self._name, self.id, filename),
            'target': 'self',
        }

    def _accounting_balances(self):
        """Saldo contable por producto y cuenta de valoración al cierre."""
        self.ensure_one()
        summaries = self.summary_ids
        accounts = summaries.account_id
        groups = self.env['account.move.line'].sudo()._read_group(
            [
                ('company_id', '=', self.company_id.id),
                ('parent_state', '=', 'posted'),
                ('account_id', 'in', accounts.ids),
                ('date', '<=', self.date_to),
            ],
            ['account_id', 'product_id'], ['balance:sum'])
        return {(account.id, product.id): balance for account, product, balance in groups}


class StockKardexAdjustmentRow(models.Model):
    _name = 'stock.kardex.adjustment.row'
    _description = 'Línea del kardex con ajustes'
    _order = 'adjustment_id, sequence'

    adjustment_id = fields.Many2one(
        comodel_name='stock.kardex.adjustment', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='adjustment_id.currency_id')
    sequence = fields.Integer()
    product_id = fields.Many2one('product.product', string='Producto', index=True)
    default_code = fields.Char(related='product_id.default_code', string='Código')
    account_id = fields.Many2one('account.account', string='Cuenta')
    row_type = fields.Selection(ROW_KINDS, string='Tipo de línea')
    date = fields.Date(string='Fecha contable')
    account_move_id = fields.Many2one('account.move', string='Asiento')
    adj_move_id = fields.Many2one('account.move', string='Asiento de ajuste')
    layer_id = fields.Many2one('stock.valuation.layer', string='Capa')
    adjusted_layer_id = fields.Many2one('stock.valuation.layer', string='Capa ajustada')
    reference = fields.Char(string='Ref. almacén')
    operation_type = fields.Char(string='Tipo operación (T12)')
    doc_type = fields.Char(string='Tipo doc.')
    doc_number = fields.Char(string='Serie-Número')
    partner = fields.Char(string='Proveedor/Cliente')
    in_qty = fields.Float(string='Entrada cant.', digits='Product Unit of Measure')
    in_value = fields.Monetary(string='Entrada costo', currency_field='currency_id')
    in_unit = fields.Float(string='Entrada C.U.', compute='_compute_units', digits='Product Price')
    out_qty = fields.Float(string='Salida cant.', digits='Product Unit of Measure')
    out_value = fields.Monetary(string='Salida costo', currency_field='currency_id')
    out_unit = fields.Float(string='Salida C.U.', compute='_compute_units', digits='Product Price')
    bal_qty = fields.Float(string='Saldo cant.', digits='Product Unit of Measure',
        aggregator=None)
    bal_value = fields.Monetary(string='Saldo costo', currency_field='currency_id',
        aggregator=None)
    bal_unit = fields.Float(string='Saldo C.U.', compute='_compute_units', digits='Product Price')
    raw_bal_value = fields.Monetary(string='Saldo a costo Odoo', currency_field='currency_id',
        aggregator=None)
    recalc_value = fields.Monetary(string='Costo recalculado', currency_field='currency_id',
        aggregator=None)
    adjust_value = fields.Monetary(string='Ajuste', currency_field='currency_id')
    odoo_create_date = fields.Datetime(string='Creación en Odoo')
    note = fields.Char(string='Observación')
    tc_invoice = fields.Float(string='TC factura', digits=(12, 6),
        aggregator=None)
    tc_receipt = fields.Float(string='TC recepción', digits=(12, 6),
        aggregator=None)
    sync_state = fields.Selection(
        selection=[
            ('new', 'Por crear'),
            ('changed', 'Por actualizar'),
            ('unchanged', 'Registrado'),
        ],
        string='Registro')
    adj_type = fields.Selection(ADJUSTMENT_TYPES, string='Tipo de ajuste')
    invoice_id = fields.Many2one('account.move', string='Factura')
    counterpart_account_id = fields.Many2one(
        'account.account', string='Contrapartida',
        help='Cuenta contra la que se registra el ajuste (en los de factura vs recepción, '
             'la de costo de ventas de ajustes con su complementario contra la 61).')
    review = fields.Selection(REVIEW_TYPES, string='Revisar')

    @api.depends('in_qty', 'in_value', 'out_qty', 'out_value', 'bal_qty', 'bal_value')
    def _compute_units(self):
        for row in self:
            row.in_unit = row.in_value / row.in_qty if row.in_qty else 0.0
            row.out_unit = row.out_value / row.out_qty if row.out_qty else 0.0
            row.bal_unit = row.bal_value / row.bal_qty if row.bal_qty else 0.0


class StockKardexAdjustmentSummary(models.Model):
    _name = 'stock.kardex.adjustment.summary'
    _description = 'Resumen del kardex por producto'
    _order = 'adjustment_id, account_id, product_id'

    adjustment_id = fields.Many2one(
        comodel_name='stock.kardex.adjustment', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='adjustment_id.currency_id')
    product_id = fields.Many2one('product.product', string='Producto')
    default_code = fields.Char(related='product_id.default_code', string='Código')
    account_id = fields.Many2one('account.account', string='Cuenta')
    opening_qty = fields.Float(string='Saldo inicial cant.', digits='Product Unit of Measure')
    opening_value = fields.Monetary(string='Saldo inicial', currency_field='currency_id')
    in_qty = fields.Float(string='Entradas cant.', digits='Product Unit of Measure')
    in_value = fields.Monetary(string='Entradas', currency_field='currency_id')
    out_qty = fields.Float(string='Salidas cant.', digits='Product Unit of Measure')
    out_value = fields.Monetary(string='Salidas según Odoo', currency_field='currency_id')
    out_recalc_value = fields.Monetary(string='Salidas recalculadas', currency_field='currency_id')
    cost_adjust = fields.Monetary(string='Ajustes de costo', currency_field='currency_id')
    return_adjust = fields.Monetary(string='Ajustes de devoluciones', currency_field='currency_id')
    fx_adjust = fields.Monetary(string='Ajustes de cambio', currency_field='currency_id')
    price_adjust = fields.Monetary(string='Ajustes de precio', currency_field='currency_id')
    production_adjust = fields.Monetary(string='Ajustes de fabricación', currency_field='currency_id')
    sales_cost = fields.Monetary(string='Costo de ventas', currency_field='currency_id')
    manual_value = fields.Monetary(string='Manuales', currency_field='currency_id')
    closing_qty = fields.Float(string='Saldo final cant.', digits='Product Unit of Measure')
    closing_value = fields.Monetary(string='Saldo final', currency_field='currency_id')
    raw_closing_value = fields.Monetary(string='Saldo final a costo Odoo', currency_field='currency_id')
    closing_unit = fields.Float(string='C.U. final', digits='Product Price')
