from odoo import fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    usd_currency_id = fields.Many2one(
        'res.currency',
        string='USD Currency',
        default=lambda self: self.env.ref('base.USD'),
    )

    expected_revenue_usd = fields.Monetary(
        string='Expected Revenue (USD)',
        currency_field='usd_currency_id',
    )
