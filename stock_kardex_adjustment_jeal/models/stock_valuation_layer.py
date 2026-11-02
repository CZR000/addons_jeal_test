# -*- coding: utf-8 -*-
from odoo import fields, models


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    kardex_adjustment_line_id = fields.Many2one(
        comodel_name='stock.kardex.adjustment.line',
        string='Ajuste de kardex',
        readonly=True,
        index='btree_not_null',
        ondelete='restrict',
        help='Línea de ajuste del kardex que creó esta capa de revaluación.',
    )
