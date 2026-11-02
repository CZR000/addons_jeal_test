from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Indica si el contacto está registrado como empleado en Recursos Humanos
    is_employee = fields.Boolean(
        string="Es Empleado",
        help="Activa esta casilla si este contacto también está registrado como empleado en Recursos Humanos.",
        default=False,
        tracking=True,
        index=True,
    )

    # Relación con el empleado registrado en Recursos Humanos
    # associated_employee_id = fields.Many2one(
    #     comodel_name="hr.employee",
    #     string="Empleado Relacionado",
    #     help="Selecciona el empleado en Recursos Humanos relacionado con este contacto. Este campo solo es relevante si el contacto está marcado como empleado.",
    #     domain="[('active', '=', True)]",
    #     ondelete="restrict",
    #     required=False,
    # )
