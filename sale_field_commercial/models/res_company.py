from odoo import _, api, fields, models, tools



class ResCompany(models.Model):
    _inherit = "res.company"

    enable_external_commercial = fields.Boolean(
        string='Habilitar Comercial',
        default=False,
        tracking=True,
        copy=False,
        index=True,
        help='Si está activo, esta compañía permite asignar contactos comerciales en las órdenes de venta.',
    )
