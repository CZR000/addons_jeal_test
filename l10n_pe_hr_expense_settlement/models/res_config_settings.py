from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hr_expense_settlement_journal_id = fields.Many2one(
        related='company_id.hr_expense_settlement_journal_id',
        readonly=False,
    )
    hr_expense_auto_settle = fields.Boolean(
        related='company_id.hr_expense_auto_settle',
        readonly=False,
    )
    hr_expense_non_register_journal_id = fields.Many2one(
        related='company_id.hr_expense_non_register_journal_id',
        readonly=False,
    )
    hr_expense_advance_account_ids = fields.Many2many(
        related='company_id.hr_expense_advance_account_ids',
        readonly=False,
    )
    hr_expense_petty_cash_account_id = fields.Many2one(
        related='company_id.hr_expense_petty_cash_account_id',
        readonly=False,
    )
    hr_expense_block_pending_advances = fields.Boolean(
        related='company_id.hr_expense_block_pending_advances', readonly=False)
    hr_expense_block_pending_days = fields.Integer(
        related='company_id.hr_expense_block_pending_days', readonly=False)
    hr_expense_block_include_petty_cash = fields.Boolean(
        related='company_id.hr_expense_block_include_petty_cash', readonly=False)
    hr_expense_petty_cash_settlement_journal_id = fields.Many2one(
        related='company_id.hr_expense_petty_cash_settlement_journal_id',
        readonly=False,
    )
