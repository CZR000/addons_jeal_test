from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class StockRequest(models.Model):
    _inherit = "stock.request"

    categ_name = fields.Char(
        related="categ_id.name",
        string="Categoria",
    )

    categ_id = fields.Many2one(
        related="product_id.categ_id",
        comodel_name="product.category",
    )
