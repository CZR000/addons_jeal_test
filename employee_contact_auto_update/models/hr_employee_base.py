from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class HrEmployeeBase(models.AbstractModel):
    _inherit = "hr.employee.base"

    def _inverse_work_contact_details(self):
        """
        Sincroniza los detalles de contacto laboral de un empleado con el modelo `res.partner`.
        Si no existe un contacto relacionado, crea automáticamente un nuevo registro en `res.partner`.
        """
        for employee in self:
            # Normalizar y extraer componentes del nombre del empleado
            first_name = (employee.firstname or "").strip().upper()
            last_name = (employee.lastname or "").strip().upper()
            second_name = (employee.secondname or "").strip().upper()

            # Construir dinámicamente el dominio de búsqueda para contactos existentes en `res.partner`
            search_domain = [("company_type", "=", "person")]

            if first_name:
                search_domain.append(("partner_name", "ilike", first_name))
            if last_name:
                search_domain.append(("first_name", "ilike", last_name))
            if second_name:
                search_domain.append(("second_name", "ilike", second_name))

            # Buscar un contacto relacionado en `res.partner`, priorizando los más recientes
            existing_contact = (
                self.env["res.partner"]
                .sudo()
                .search(search_domain, limit=1, order="create_date DESC")
            )

            # Si no existe un contacto asociado
            if not employee.work_contact_id:
                if existing_contact:
                    # Asignar el contacto existente al empleado
                    employee.work_contact_id = existing_contact.id
                    employee.address_home_id = existing_contact.id

                    # Marcar el contacto como empleado
                    existing_contact.sudo().write({"is_employee": True})
                else:
                    # Construir el nombre completo en formato "APELLIDO SEGUNDO_APELLIDO, NOMBRE"
                    full_name = f"{last_name} {second_name}, {first_name}".strip()

                    # Crear los datos para un nuevo contacto
                    new_contact_data = {
                        "email": employee.work_email,
                        "mobile": employee.mobile_phone,
                        "name": full_name,
                        "partner_name": first_name,
                        "first_name": last_name,
                        "second_name": second_name,
                        "image_1920": employee.image_1920,
                        "company_id": employee.company_id.id,
                    }

                    # Crear y asignar el nuevo contacto al empleado
                    new_contact = (
                        self.env["res.partner"]
                        .sudo()
                        .with_context(tools.clean_context(self._context))
                        .create(new_contact_data)
                    )
                    employee.work_contact_id = new_contact.id
                    employee.address_home_id = new_contact.id
            else:
                # Actualizar los datos básicos del contacto asignado si ya existe
                updated_contact_data = {
                    "email": employee.work_email,
                    "mobile": employee.mobile_phone,
                }
                employee.work_contact_id.sudo().write(updated_contact_data)
