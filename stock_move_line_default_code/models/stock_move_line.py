from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    product_default_code = fields.Char(
        related='product_id.default_code',
        string='Internal Reference',
        store=False,
    )
