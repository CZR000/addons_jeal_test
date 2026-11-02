# -*- coding: utf-8 -*-
from odoo import fields, models


class HelpdeskStage(models.Model):
    _inherit = 'helpdesk.stage'

    x_require_approval = fields.Boolean(
        string='Requiere Aprobación',
        default=False,
        help='Al mover un ticket a esta etapa se generará una solicitud de aprobación automáticamente.',
    )
    x_is_approved_stage = fields.Boolean(
        string='Etapa Aprobado',
        default=False,
        help='Marca esta etapa como destino cuando la solicitud de aprobación sea aprobada.',
    )
    x_is_refused_stage = fields.Boolean(
        string='Etapa Rechazado',
        default=False,
        help='Marca esta etapa como destino cuando la solicitud de aprobación sea rechazada.',
    )
    x_is_in_progress_stage = fields.Boolean(
        string='Etapa En Proceso',
        default=False,
        help='Marca esta etapa como destino automático cuando el reclutador registra el primer candidato para el puesto solicitado.',
    )
    x_is_cancel_stage = fields.Boolean(
        string='Etapa Cancelado',
        default=False,
        help='Marca esta etapa como la de cancelación manual. Solo quien creó el ticket puede moverlo aquí.',
    )
