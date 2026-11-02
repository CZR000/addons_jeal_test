from odoo import _, api, fields, models, tools


class HrContract(models.Model):
    _inherit = "hr.contract"

    renewal_status = fields.Selection(
        selection=[
            ("none", "No Evaluado"),
            ("pending_renew", "Pendiente Renovar"),
            ("to_renew", "A Renovar"),
            ("not_renew", "No Renovar"),
        ],
        string="Estado de Renovación",
        default="none",
        copy=False,
        tracking=True,
        help=(
            "Define el estado de renovación del contrato:\n"
            "- 'No Evaluado': No se ha definido acción aún.\n"
            "- 'Pendiente Renovar': No se ha definido acción aún esta pendiente.\n"
            "- 'A Renovar': Será renovado automáticamente si cumple condiciones.\n"
            "- 'No Renovar': Excluye este contrato del proceso de renovación."
        ),
    )
