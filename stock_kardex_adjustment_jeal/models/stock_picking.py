# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    kardex_fx_invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura para tipo de cambio',
        copy=False,
        check_company=True,
        domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted')]",
        help='Factura de proveedor cuyo tipo de cambio se usa en el ajuste del '
             'kardex de esta recepción. Tiene prioridad sobre la indicada en la '
             'orden de compra.',
    )
