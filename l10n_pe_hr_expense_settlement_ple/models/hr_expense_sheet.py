from odoo import api, models


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    @api.model
    def _l10n_pe_prepare_expenses_bill_vals(self, expenses):
        vals = super()._l10n_pe_prepare_expenses_bill_vals(expenses)
        classification = self.env['product.product']._get_expense_classification(expenses)
        if classification:
            vals['types_goods_services_id'] = classification.id
        return vals
