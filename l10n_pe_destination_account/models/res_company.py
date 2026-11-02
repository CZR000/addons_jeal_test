from odoo import _, api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    destination_account_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario para Distribución",
        check_company=True,
        domain="[('type', '=', 'general')]",
        help=(
            "Diario contable por defecto donde se registrarán los asientos "
            "automáticos generados por la distribución contable."
        ),
    )
