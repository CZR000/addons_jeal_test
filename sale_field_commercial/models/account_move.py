from odoo import _, api, fields, models, tools, Command
from odoo.exceptions import UserError, ValidationError



class AccountMove(models.Model):
    _inherit = "account.move"

    enable_external_commercial = fields.Boolean(
        related="company_id.enable_external_commercial",
    )

    external_commercial_id = fields.Many2one(
        comodel_name="res.partner",
        string='Comercial',
        readonly=True,
        tracking=True,
        domain="""[
            ('company_id', 'in', [company_id, False]),
        ]""",
        help='Contacto comercial o vendedor externo no vinculado a un usuario del sistema. Se utiliza para indicar quién gestionó la venta.',
    )
