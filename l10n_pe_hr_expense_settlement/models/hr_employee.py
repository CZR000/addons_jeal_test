from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    expense_analytic_distribution = fields.Json(
        string='Centro de costos',
        groups='hr.group_hr_user',
        help='Distribución analítica que se propone automáticamente en los gastos '
             'de este empleado.',
    )
    # Requerido por el widget analytic_distribution (ver analytic.mixin).
    analytic_precision = fields.Integer(
        store=False,
        default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic'),
    )
    l10n_pe_petty_cash_balance = fields.Monetary(
        string='Saldo del fondo de caja chica',
        currency_field='l10n_pe_company_currency_id',
        compute='_compute_l10n_pe_petty_cash_balance',
        groups='account.group_account_invoice',
        help='Saldo de caja chica del empleado sumando todas sus líneas: desembolsos y reposiciones '
             'menos lo rendido.',
    )
    l10n_pe_company_currency_id = fields.Many2one(
        related='company_id.currency_id', string='Moneda del fondo de gastos',
    )

    def _compute_l10n_pe_petty_cash_balance(self):
        for employee in self:
            employee.l10n_pe_petty_cash_balance = employee._l10n_pe_get_petty_cash_balance(employee.company_id)

    def _l10n_pe_get_petty_cash_lines(self, company):
        """Apuntes abiertos del fondo de caja chica del empleado: el fondo se repone
        con pagos nuevos, así que su saldo queda repartido en varias líneas."""
        self.ensure_one()
        partner = self.sudo().work_contact_id
        if not partner or not company:
            return self.env['account.move.line']
        lines = self.env['account.move.line'].sudo().search([
            ('company_id', '=', company.id),
            ('partner_id', '=', partner.id),
            ('account_id', 'in', company._get_hr_expense_employee_accounts().ids),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
        ])
        petty_cash_account = company.hr_expense_petty_cash_account_id
        return lines.filtered(lambda line: (
            line.account_id == petty_cash_account or line._l10n_pe_get_advance_kind() == 'petty_cash'
        ))

    def _l10n_pe_get_petty_cash_balance(self, company):
        """Saldo total del fondo de caja chica (en la moneda de la compañía)."""
        self.ensure_one()
        return sum(self._l10n_pe_get_petty_cash_lines(company).mapped('amount_residual'))
