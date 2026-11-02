from odoo import fields, models


class MulticurrencyRevaluationWizard(models.TransientModel):
    _inherit = 'account.multicurrency.revaluation.wizard'

    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Cuenta analítica',
    )

    def _get_move_vals(self):
        move_vals = super()._get_move_vals()

        if not self.analytic_account_id:
            return move_vals

        analytic_distribution = {str(self.analytic_account_id.id): 100.0}
        # In Odoo 18 the wizard creates both expense and income provision lines.
        provision_account_ids = {
            self.expense_provision_account_id.id,
            self.income_provision_account_id.id,
        }

        for command in move_vals.get('line_ids', []):
            # command is (0, 0, vals) — Command.create() still returns a tuple
            line_vals = command[2]
            if line_vals.get('account_id') in provision_account_ids:
                line_vals['analytic_distribution'] = analytic_distribution

        return move_vals
