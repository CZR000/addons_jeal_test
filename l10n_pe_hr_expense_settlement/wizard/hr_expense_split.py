from odoo import api, models


class HrExpenseSplit(models.TransientModel):
    _inherit = 'hr.expense.split'

    @api.onchange('product_id')
    def _onchange_product_id(self):
        # El nativo conserva los impuestos del gasto original aun al cambiar de
        # categoría: con otra categoría el IGV debe ser el de la nueva.
        if self.product_id == self.expense_id.product_id:
            return super()._onchange_product_id()
        self.tax_ids = self.product_id._l10n_pe_get_expense_taxes(self.company_id)


class HrExpenseSplitWizard(models.TransientModel):
    _inherit = 'hr.expense.split.wizard'

    def action_split_expense(self):
        expense = self.expense_id
        # Al volver a dividir una línea se conserva el comprobante original.
        receipt_total = expense.l10n_pe_receipt_total_amount or self.total_amount_currency_original
        origin = expense.l10n_pe_split_origin_id or expense
        action = super().action_split_expense()
        if expense._l10n_pe_is_vendor_receipt():
            # Las líneas deben seguir sumando el total del comprobante.
            split_expenses = self.env['hr.expense'].browse(action['domain'][0][2]) | expense
            split_expenses.write({'l10n_pe_receipt_total_amount': receipt_total})
            (split_expenses - origin).l10n_pe_split_origin_id = origin
        return action
