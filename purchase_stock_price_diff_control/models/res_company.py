from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    pdiff_block_reset_to_draft = fields.Boolean(
        string="Bloquear reinicio a borrador de facturas valorizadas",
        default=False,
        help="Impide pasar a borrador facturas de proveedor que ya generaron "
        "capas de valorización de inventario. Los usuarios del grupo "
        "«Puede reiniciar a borrador facturas valorizadas» no se ven afectados.",
    )
