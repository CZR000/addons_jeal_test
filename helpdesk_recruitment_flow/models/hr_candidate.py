# -*- coding: utf-8 -*-
from odoo import fields, models


class HrCandidate(models.Model):
    _inherit = 'hr.candidate'

    # El nombre es obligatorio desde la primera etapa (calificación inicial)
    # según la matriz de campos del reclutamiento. candidate_id ya es required
    # en hr.applicant, pero eso no impedía guardar un candidato sin nombre.
    partner_name = fields.Char(required=True)
