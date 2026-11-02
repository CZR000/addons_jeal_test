from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_carrier = fields.Boolean(
        string='Es Transportista',
        default=False,
        help='Indica si el contacto es un transportista.',
    )
