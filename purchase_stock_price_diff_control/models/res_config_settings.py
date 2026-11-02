from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pdiff_block_reset_to_draft = fields.Boolean(
        related="company_id.pdiff_block_reset_to_draft",
        readonly=False,
    )
