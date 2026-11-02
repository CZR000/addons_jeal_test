from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hr_expense_ic_receive = fields.Boolean(related='company_id.hr_expense_ic_receive', readonly=False)
    hr_expense_ic_journal_id = fields.Many2one(related='company_id.hr_expense_ic_journal_id', readonly=False)
    hr_expense_ic_receivable_account_id = fields.Many2one(
        related='company_id.hr_expense_ic_receivable_account_id', readonly=False)
    hr_expense_ic_receivable_foreign_account_id = fields.Many2one(
        related='company_id.hr_expense_ic_receivable_foreign_account_id', readonly=False)
    hr_expense_ic_payable_account_id = fields.Many2one(
        related='company_id.hr_expense_ic_payable_account_id', readonly=False)
    hr_expense_ic_payable_foreign_account_id = fields.Many2one(
        related='company_id.hr_expense_ic_payable_foreign_account_id', readonly=False)
    hr_expense_ic_default_product_id = fields.Many2one(
        related='company_id.hr_expense_ic_default_product_id', readonly=False)
