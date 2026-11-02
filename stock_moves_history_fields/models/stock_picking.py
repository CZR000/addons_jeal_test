from odoo import models, fields


class StockPicking(models.Model):
    _inherit = "stock.picking"

    code_movement_type = fields.Selection(
        string="Código de movimiento",
        selection=[
            ("A", "A"),
            ("M", "M"),
            ("C", "C"),
        ],
        default="M",
    )
