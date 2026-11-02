# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    # Nombre (vía candidate_id) y Etapa son obligatorios desde la primera etapa
    # (calificación inicial) según la matriz de campos del reclutamiento.
    stage_id = fields.Many2one(required=True)

    # ── Nuevos campos de información del candidato ───────────────────────────
    x_birthday = fields.Date(string='Fecha de nacimiento')
    x_distrito = fields.Char(string='Distrito')
    x_identification_doc = fields.Char(string='DNI')

    # ── Vínculo con el ticket de Mesa de Ayuda que originó la solicitud ──────
    x_helpdesk_ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string='Ticket de Origen',
        copy=False,
        readonly=True,
    )

    # ── Contrato: solo obligatorios y visibles en la etapa Carta Oferta ──────
    x_work_system_id = fields.Many2one(
        'hr.recruitment.work.system',
        string='Sistema de Trabajo',
    )
    x_contract_modality_id = fields.Many2one(
        'hr.recruitment.contract.modality',
        string='Modalidad de Contrato',
    )
    x_work_modality_id = fields.Many2one(
        'hr.recruitment.work.modality',
        string='Modalidad de Trabajo',
    )

    # ── Flags de etapa (computed, no stored) ─────────────────────────────────
    x_stage_is_carta_oferta = fields.Boolean(
        compute='_compute_x_stage_flags',
        string='Etapa Carta Oferta',
    )
    x_stage_is_contrato_firmado = fields.Boolean(
        compute='_compute_x_stage_flags',
        string='Etapa Contrato Firmado',
    )
    x_stage_is_medical_exam = fields.Boolean(
        compute='_compute_x_stage_flags',
        string='Etapa Examen Médico',
    )

    # ── Examen médico ────────────────────────────────────────────────────────
    x_medical_exam_result = fields.Selection([
        ('apto', 'Apto'),
        ('apto_restricciones', 'Apto con restricciones'),
        ('apto_observaciones', 'Apto con observaciones'),
        ('observado', 'Observado'),
        ('no_apto', 'No apto'),
    ], string='Resultado Examen Médico')
    x_medical_exam_note = fields.Text(string='Observación / Restricción del Examen')
    x_medical_exam_exception = fields.Boolean(
        string='Excepción Examen Médico',
        help='Permite avanzar de etapa aunque el resultado del examen médico sea distinto de "Apto" '
             '(no aplica si el resultado es "No apto").',
    )

    # ── Entrevistadores y calificaciones (reemplazo de campos de Odoo Studio) ─
    x_entrevistador_1 = fields.Many2one('res.users', string='Entrevistador 1')
    x_calificacion_entrevista_1 = fields.Selection([
        ('0', 'Normal'), ('1', 'Bueno'), ('2', 'Muy bueno'), ('3', 'Excelente'),
    ], string='Calificación Entrevista 1')
    x_entrevistador_2 = fields.Many2one('res.users', string='Entrevistador 2')
    x_calificacion_entrevista_2 = fields.Selection([
        ('0', 'Normal'), ('1', 'Bueno'), ('2', 'Muy bueno'), ('3', 'Excelente'),
    ], string='Calificación Entrevista 2')
    x_entrevistador_3 = fields.Many2one('res.users', string='Entrevistador 3')
    x_calificacion_entrevista_3 = fields.Selection([
        ('0', 'Normal'), ('1', 'Bueno'), ('2', 'Muy bueno'), ('3', 'Excelente'),
    ], string='Calificación Entrevista 3')

    x_slot_1_is_mine = fields.Boolean(compute='_compute_x_slot_is_mine')
    x_slot_2_is_mine = fields.Boolean(compute='_compute_x_slot_is_mine')
    x_slot_3_is_mine = fields.Boolean(compute='_compute_x_slot_is_mine')

    @api.depends('x_entrevistador_1', 'x_entrevistador_2', 'x_entrevistador_3')
    def _compute_x_slot_is_mine(self):
        for rec in self:
            rec.x_slot_1_is_mine = rec.x_entrevistador_1.id == self.env.uid
            rec.x_slot_2_is_mine = rec.x_entrevistador_2.id == self.env.uid
            rec.x_slot_3_is_mine = rec.x_entrevistador_3.id == self.env.uid

    @api.depends('stage_id')
    def _compute_x_stage_flags(self):
        for rec in self:
            rec.x_stage_is_carta_oferta = rec.stage_id.x_is_carta_oferta
            rec.x_stage_is_contrato_firmado = rec.stage_id.x_is_contrato_firmado
            rec.x_stage_is_medical_exam = rec.stage_id.x_is_medical_exam_stage

    def action_send_sign_request(self):
        self.ensure_one()
        return self._send_applicant_sign_request()

    def action_send_survey(self):
        self.ensure_one()
        action = super().action_send_survey()
        if self.user_id.partner_id:
            action['context'] = dict(action['context'], default_partner_ids=self.user_id.partner_id.ids)
        return action

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for applicant in records:
            applicant._link_helpdesk_ticket()
        return records

    def write(self, vals):
        if 'stage_id' in vals:
            for applicant in self:
                current_stage = applicant.stage_id
                if current_stage and current_stage.x_is_medical_exam_stage and vals['stage_id'] != current_stage.id:
                    applicant._check_medical_exam_clearance()
        self._check_interviewer_slots(vals)
        return super().write(vals)

    def _check_interviewer_slots(self, vals):
        if self.env.user.has_group('base.group_system'):
            return
        for slot in (1, 2, 3):
            interviewer_field = f'x_entrevistador_{slot}'
            rating_field = f'x_calificacion_entrevista_{slot}'
            touches_interviewer = interviewer_field in vals
            touches_rating = rating_field in vals
            if not touches_interviewer and not touches_rating:
                continue
            for applicant in self:
                current_interviewer = applicant[interviewer_field]
                if touches_interviewer and current_interviewer and current_interviewer.id != self.env.uid:
                    raise UserError(_(
                        'Solo %s puede reasignar el Entrevistador %s.'
                    ) % (current_interviewer.name, slot))
                if touches_rating:
                    effective_interviewer_id = vals[interviewer_field] if touches_interviewer else current_interviewer.id
                    if not effective_interviewer_id:
                        raise UserError(_(
                            'Debe asignarse un Entrevistador %s antes de poder calificar esa entrevista.'
                        ) % slot)
                    if effective_interviewer_id != self.env.uid:
                        raise UserError(_(
                            'Solo el Entrevistador %s asignado puede calificar la Entrevista %s.'
                        ) % (slot, slot))

    def _check_medical_exam_clearance(self):
        self.ensure_one()
        if self.x_medical_exam_result == 'apto':
            return
        if self.x_medical_exam_exception and self.x_medical_exam_result in ('apto_restricciones', 'apto_observaciones', 'observado'):
            return
        raise UserError(_(
            'No se puede avanzar de etapa: el resultado del examen médico no es "Apto". '
            'Active la excepción si corresponde (no aplica para "No apto").'
        ))

    def _link_helpdesk_ticket(self):
        self.ensure_one()
        if self.x_helpdesk_ticket_id or not self.job_id:
            return

        # El ticket aprobado más reciente para este puesto es el que ancla a todos los
        # candidatos de esa terna, tenga o no ya candidatos vinculados. Se usa la etapa
        # actual (no solo x_approval_date) para no depender de que el ticket haya sido
        # aprobado específicamente por este módulo.
        ticket = self.env['helpdesk.ticket'].sudo().search([
            ('x_perfil_id', '=', self.job_id.id),
            ('stage_id.x_is_approved_stage', '=', True),
        ], order='x_approval_date desc, id desc', limit=1)
        if not ticket:
            return

        is_first_applicant_for_ticket = not ticket.x_applicant_ids

        vals = {'x_helpdesk_ticket_id': ticket.id}
        if not self.solicitante_id and ticket.create_uid:
            employee = self.env['hr.employee'].sudo().search([
                ('user_id', '=', ticket.create_uid.id),
            ], limit=1)
            if employee:
                vals['solicitante_id'] = employee.id
        if not self.fecha_solicitud_formal and ticket.create_date:
            vals['fecha_solicitud_formal'] = ticket.create_date.date()
        if not self.fecha_aprobacion and ticket.x_approval_date:
            vals['fecha_aprobacion'] = ticket.x_approval_date
        self.write(vals)

        if is_first_applicant_for_ticket:
            ticket._move_to_in_progress_stage()
