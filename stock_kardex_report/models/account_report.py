from odoo import fields, models


class AccountReport(models.Model):
    _inherit = 'account.report'

    kardex_use_accounting_date = fields.Boolean(
        string='Kardex Uses Accounting Date',
        default=False,
        help='If enabled, the kardex computes costs and balances using each '
             'valuation layer accounting date instead of the creation date.',
    )
