from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.onchange("address_home_id")
    def _onchange_work_contact_id(self):
        """
        Actualiza los detalles del empleado (nombres y apellidos)
        basándose en los datos del contacto seleccionado en `address_home_id`.
        """
        if (
            self.address_home_id
            and self.address_home_id != self._origin.address_home_id
        ):
            # Actualizar los campos del empleado con los datos del contacto
            self.firstname = self.address_home_id.partner_name or ""
            self.lastname = self.address_home_id.first_name or ""
            self.secondname = self.address_home_id.second_name or ""
