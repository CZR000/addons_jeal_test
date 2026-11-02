from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class StockRequestOrder(models.Model):
    _inherit = "stock.request.order"

    product_ids = fields.Many2one(
        comodel_name="product.product",
        related="stock_request_ids.product_id",
        string="Producto",
    )
