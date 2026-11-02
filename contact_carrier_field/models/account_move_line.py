from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    is_carrier = fields.Boolean(
        string='Es Transportista',
        related='move_id.is_carrier',
        store=True,
        readonly=True,
    )