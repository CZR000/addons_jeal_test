from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_sales_manager = fields.Boolean(
        string='Gerente de Ventas',
        default=False,
        help='Si está marcado, este usuario puede modificar listas de precios '
             'y aprobar/rechazar descuentos que superen el límite configurado.',
    )
