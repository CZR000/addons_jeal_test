from odoo import models, fields


class AccountRevaluationClosingRate(models.Model):
    _name = 'account.revaluation.closing.rate'
    _description = 'Revaluation Closing Rate'
    _order = 'date desc, id desc'

    move_id = fields.Many2one(
        'account.move',
        string='Adjustment Entry',
        ondelete='cascade',
        required=True,
        index=True,
    )
    date = fields.Date(string='Date', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True)
    # Stored as "units of company currency per 1 unit of foreign currency" (e.g. PEN per USD = 3.28)
    sale_rate = fields.Float(string='Sale Rate', digits=(16, 6))
    purchase_rate = fields.Float(string='Purchase Rate', digits=(16, 6))
