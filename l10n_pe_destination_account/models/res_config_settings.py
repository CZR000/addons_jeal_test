from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    destination_account_journal_id = fields.Many2one(
        comodel_name="account.journal",
        related="company_id.destination_account_journal_id",
        string="Diario para Distribución",
        readonly=False,
        check_company=True,
        domain="[('type', '=', 'general')]",
        help=(
            "Seleccione el diario donde se contabilizarán los asientos automáticos "
            "relacionados con la distribución contable definida en cuentas destino."
        ),
    )
