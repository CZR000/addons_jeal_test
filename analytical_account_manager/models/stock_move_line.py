from odoo import _, api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    # Eliminar campos
    is_analytic_account = fields.Boolean(
        related="picking_id.is_analytic_account",
        string="Es cuenta analítica?",
    )

    show_analytic_section = fields.Boolean(
        related="picking_id.show_analytic_section",
        string="Mostrar sección analítica?",
    )
    # Hasta aca

    analytic_plan_id = fields.Many2one(
        comodel_name="account.analytic.plan",
        string="Plan Analítico",
    )

    analytic_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Cuenta Analítica",
        domain="[('plan_id', '=', analytic_plan_id)]",
    )
