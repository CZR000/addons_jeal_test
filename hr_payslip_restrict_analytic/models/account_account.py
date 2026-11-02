from odoo import _, api, fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    enable_analytic_entries = fields.Boolean(
        string="Habilitar Cuentas Analíticas en Nómina",
        default=False,
        tracking=True,
        copy=False,
        index=True,
        store=True,
        help="Si está activado, esta cuenta contable permitirá asignaciones analíticas al generar asientos contables desde nóminas. "
        "Esto facilita la distribución de costos en cuentas analíticas específicas.",
    )
