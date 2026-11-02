from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hr_expense_rate_policy = fields.Selection(
        related='company_id.hr_expense_rate_policy',
        readonly=False,
    )
