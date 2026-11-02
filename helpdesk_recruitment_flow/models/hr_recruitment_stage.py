# -*- coding: utf-8 -*-
from odoo import fields, models


class HrRecruitmentStage(models.Model):
    _inherit = 'hr.recruitment.stage'

    x_is_carta_oferta = fields.Boolean(
        string='Es Carta Oferta',
        default=False,
        help='Activa para mostrar los campos de Salario y Disponibilidad en esta etapa.',
    )
    x_is_contrato_firmado = fields.Boolean(
        string='Es Contrato Firmado',
        default=False,
        help='Activa para mostrar el botón de Solicitud de Firma en esta etapa.',
    )
    x_is_medical_exam_stage = fields.Boolean(
        string='Es Etapa de Examen Médico',
        default=False,
        help='Activa para bloquear el avance de candidatos con resultado de examen médico distinto de "Apto", salvo excepción.',
    )
    x_is_third_interview_stage = fields.Boolean(
        string='Es Tercera Entrevista',
        default=False,
    )
