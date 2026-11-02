from odoo import fields, models


class CrmStage(models.Model):
    _inherit = "crm.stage"

    stage_probability = fields.Float(
        string="Probabilidad (%)",
        help="Al mover un lead/oportunidad a esta etapa, su probabilidad se actualizará con este valor.",
    )
