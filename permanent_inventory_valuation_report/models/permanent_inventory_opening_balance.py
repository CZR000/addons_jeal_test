from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_round


class PermanentInventoryOpeningBalance(models.Model):
    _name = "permanent.inventory.opening.balance"
    _description = "Valuación de productos en stock"

    ple_stock_products = fields.Many2one(
        string="Valuation book",
        comodel_name="permanent.inventory.valuation",
    )

    product_id = fields.Integer(
        string="Id Producto",
    )

    product_valuation = fields.Char(
        string="Producto",
    )

    quantity_product_hand = fields.Float(
        string="Cantidad a mano",
    )

    udm_product = fields.Char(
        string="UDM",
    )

    standard_price = fields.Float(
        string="Costo unitario",
    )

    total_value = fields.Float(
        string="Valor total",
        compute="_compute_total_value",
    )

    code_exist = fields.Integer(
        string="Código de existencia",
    )

    def _compute_total_value(self):
        for data in self:
            data.total_value = float_round(
                data.quantity_product_hand * data.standard_price, 2
            )
