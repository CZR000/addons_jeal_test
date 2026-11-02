# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    kardex_fx_invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura para tipo de cambio',
        copy=False,
        check_company=True,
        domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), "
               "('partner_id.commercial_partner_id', '=', commercial_partner_id)]",
        help='Factura de proveedor cuyo tipo de cambio se usa en el ajuste del '
             'kardex de las recepciones de esta orden, cuando la factura se '
             'registró en otra orden de compra (por ejemplo, una OC duplicada).',
    )
    commercial_partner_id = fields.Many2one(
        related='partner_id.commercial_partner_id')
