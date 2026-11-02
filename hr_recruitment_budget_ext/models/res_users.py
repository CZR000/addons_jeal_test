from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    can_create_employee = fields.Boolean(
        string='Puede Crear Empleado',
        default=False,
        help=(
            'Si está marcado, el usuario podrá usar el botón "Crear Empleado" '
            'en las solicitudes de reclutamiento. Si no está marcado, el botón '
            'no será visible aunque tenga acceso al módulo de reclutamiento.'
        ),
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['can_create_employee']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['can_create_employee']
