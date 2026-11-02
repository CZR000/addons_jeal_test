from odoo import models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _prepare_exchange_difference_move_vals(self, amounts_list, company=None, exchange_date=None, **kwargs):
        # Inject the company-level exchange difference analytic account using
        # Odoo 18's built-in exchange_analytic_distribution kwarg. This hook
        # covers the main reconciliation path (_reconcile_plan →
        # _create_exchange_difference_moves → _prepare_exchange_difference_move_vals).
        company_rec = self.company_id[:1] or company or self.env.company
        analytic_account = company_rec.exchange_diff_analytic_account_id
        if analytic_account:
            kwargs['exchange_analytic_distribution'] = {str(analytic_account.id): 100.0}
        return super()._prepare_exchange_difference_move_vals(
            amounts_list, company=company, exchange_date=exchange_date, **kwargs
        )
