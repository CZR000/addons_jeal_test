# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    allowed_account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='analytic_account_allowed_accounts_rel',
        column1='analytic_account_id',
        column2='account_id',
        string='Cuentas de gastos permitidas',
        help=(
            "Si este campo está vacío, la cuenta analítica puede usarse con "
            "cualquier cuenta contable. Si se especifican cuentas, solo se "
            "permitirá usar esta analítica en líneas de asientos cuya cuenta "
            "contable esté en esta lista."
        ),
    )
