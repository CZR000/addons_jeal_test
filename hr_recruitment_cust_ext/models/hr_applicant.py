# -*- coding: utf-8 -*-
from odoo import fields, models


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    # Responsables
    solicitante_id = fields.Many2one(
        'hr.employee',
        string='Solicitante',
    )
    jefe_directo_id = fields.Many2one(
        'hr.employee',
        string='Jefe directo',
    )
    proveedor_id = fields.Many2one(
        'res.partner',
        string='Proveedor',
    )

    # Fechas del proceso
    fecha_solicitud_formal = fields.Date(string='Fecha de solicitud formal')
    fecha_aprobacion = fields.Date(string='Fecha de aprobación')
    fecha_publicacion = fields.Date(string='Fecha de publicación')
    fecha_envio_req_proveedor = fields.Date(string='Fecha de envío req. proveedor')
    fecha_recepcion_terna = fields.Date(string='Fecha de recepción de terna')
    fecha_envio_terna_jefatura = fields.Date(string='Fecha de envío terna a jefatura')
    fecha_respuesta_jefatura = fields.Date(string='Fecha de respuesta de jefatura')
    fecha_ini_entrevista_jd = fields.Date(string='Fecha inicio entrevista JD')
    fecha_fin_entrevista_jd = fields.Date(string='Fecha fin entrevista JD')
    fecha_entrevista_psico = fields.Date(string='Fecha de entrevista psicológica')
    fecha_eleccion = fields.Date(string='Fecha de elección')
    fecha_notif_carta_oferta = fields.Date(string='Fecha de notif. carta oferta')
    fecha_resultado_examen = fields.Date(string='Fecha de resultado de examen')
    fecha_ingreso = fields.Date(string='Fecha de ingreso')
    fecha_cierre_vacante = fields.Date(string='Fecha de cierre de vacante')
