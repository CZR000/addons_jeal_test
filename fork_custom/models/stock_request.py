from odoo import _, fields, models


class StockRequest(models.Model):
    _inherit = "stock.request"

    marca = fields.Char("Marca")
