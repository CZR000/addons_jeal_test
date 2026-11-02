from odoo import models


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    def _l10n_pe_get_settle_balance_context(self, payment_type):
        return {
            **super()._l10n_pe_get_settle_balance_context(payment_type),
            'default_l10n_pe_expense_rate_type': self.company_id._get_hr_expense_rate_type(payment_type),
        }

    def _l10n_pe_prepare_refund_payment_vals(self, refund, partner, advances):
        vals = super()._l10n_pe_prepare_refund_payment_vals(refund, partner, advances)
        if refund.currency_id != self.company_currency_id:
            vals['exchange_rate_type'] = self.company_id._get_hr_expense_rate_type('inbound')
        return vals
