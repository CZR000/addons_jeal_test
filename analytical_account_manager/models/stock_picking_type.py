from odoo import _, api, fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    is_analytic_account = fields.Boolean(
        string="¿Usa Cuenta Analítica?",
        default=False,
        help="Permite asignar cuentas analíticas en las transferencias de este tipo de operación.",
    )
