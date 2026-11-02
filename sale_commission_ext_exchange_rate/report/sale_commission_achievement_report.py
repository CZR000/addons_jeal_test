from odoo import api, models


class SaleCommissionAchievementReport(models.Model):
    _inherit = 'sale.commission.achievement.report'

    @api.model
    def _currency_rate_where(self):
        return f"{super()._currency_rate_where()} AND r.exchange_rate = 'sale'"
