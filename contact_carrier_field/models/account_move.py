from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_carrier = fields.Boolean(
        string='Es Transportista',
        related='partner_id.is_carrier',
        store=True,
        readonly=True,
    )