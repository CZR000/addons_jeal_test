# -*- coding: utf-8 -*-
from odoo import fields, models


class ApprovalCategory(models.Model):
    _inherit = 'approval.category'

    x_is_recruitment = fields.Boolean(
        string='Es de Reclutamiento',
        help='Marca este tipo de aprobación como disponible para seleccionarse en los tickets de reclutamiento de la Mesa de Ayuda.',
    )
