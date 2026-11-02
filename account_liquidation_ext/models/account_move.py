from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    liquidation_name = fields.Char(
        string='Liquidaci\u00f3n',
        readonly=True,
        copy=False,
    )
