from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class HrCandidate(models.Model):
    _inherit = 'hr.candidate'

    current_user_can_create_employee = fields.Boolean(
        compute='_compute_current_user_can_create_employee',
        string='Usuario puede crear empleado',
    )

    @api.depends_context('uid')
    def _compute_current_user_can_create_employee(self):
        can_create = self.env.user.can_create_employee
        for record in self:
            record.current_user_can_create_employee = can_create

    def create_employee_from_candidate(self):
        if not self.env.user.can_create_employee:
            raise AccessError(_(
                'No tiene permiso para crear empleados desde un candidato. '
                'Contacte al administrador para activar el permiso "Puede Crear Empleado" en su usuario.'
            ))
        return super().create_employee_from_candidate()
