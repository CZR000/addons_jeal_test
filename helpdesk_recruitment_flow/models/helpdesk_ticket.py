# -*- coding: utf-8 -*-
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    x_perfil_id = fields.Many2one(
        'hr.job',
        string='Perfil',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
    )
    x_departamento_id = fields.Many2one(
        'hr.department',
        string='Departamento',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
    )
    x_approval_category_id = fields.Many2one(
        'approval.category',
        string='Tipo de Solicitud',
        domain="[('x_is_recruitment', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
        help='Tipo de aprobación a utilizar al generar la solicitud de aprobación de este ticket.',
    )
    x_approval_request_id = fields.Many2one(
        'approval.request',
        string='Solicitud de Aprobación',
        copy=False,
        readonly=True,
    )
    x_approval_date = fields.Date(
        string='Fecha de Aprobación',
        copy=False,
        readonly=True,
    )
    x_applicant_ids = fields.One2many(
        'hr.applicant',
        'x_helpdesk_ticket_id',
        string='Candidatos de Reclutamiento',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for ticket in records:
            if ticket.stage_id and ticket.stage_id.x_require_approval:
                ticket._handle_approval_stage()
        return records

    def write(self, vals):
        if 'stage_id' in vals and not self.env.context.get('hrf_bypass_stage_guard'):
            self._check_manual_stage_change(vals['stage_id'])

        old_stages = {ticket.id: ticket.stage_id.id for ticket in self}
        result = super().write(vals)
        if 'stage_id' in vals:
            for ticket in self:
                old_stage_id = old_stages.get(ticket.id)
                new_stage = ticket.stage_id
                if new_stage.id != old_stage_id and new_stage.x_require_approval:
                    ticket._handle_approval_stage()

        # Si Perfil o Departamento se editan DESPUÉS de que ya se generó la
        # solicitud de aprobación (por ejemplo, el ticket se creó directo en una
        # etapa que requiere aprobación y estos campos se llenaron después), hay
        # que reflejar el cambio en la aprobación ya creada, mientras siga pendiente.
        if 'x_perfil_id' in vals or 'x_departamento_id' in vals:
            for ticket in self:
                approval = ticket.x_approval_request_id
                if approval and approval.request_status not in ('approved', 'refused', 'cancel'):
                    approval.write({
                        'x_perfil_id': ticket.x_perfil_id.id if ticket.x_perfil_id else False,
                        'x_departamento_id': ticket.x_departamento_id.id if ticket.x_departamento_id else False,
                    })
        return result

    def _check_manual_stage_change(self, new_stage_id):
        new_stage = self.env['helpdesk.stage'].browse(new_stage_id)
        if new_stage.x_is_approved_stage or new_stage.x_is_refused_stage or new_stage.x_is_in_progress_stage:
            raise UserError(_(
                'La etapa "%s" se asigna automáticamente por el flujo de aprobación/reclutamiento '
                'y no puede moverse manualmente.'
            ) % new_stage.name)
        if new_stage.x_is_cancel_stage:
            for ticket in self:
                if self.env.user != ticket.create_uid and not self.env.user.has_group('base.group_system'):
                    raise UserError(_(
                        'Solo el usuario que generó el ticket puede moverlo a la etapa "%s".'
                    ) % new_stage.name)

    def action_open_approval_request(self):
        self.ensure_one()
        if not self.x_approval_request_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'approval.request',
            'res_id': self.x_approval_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _handle_approval_stage(self):
        self.ensure_one()
        stage = self.stage_id
        category = self.x_approval_category_id
        if not category:
            raise UserError(_(
                'Debe seleccionar el "Tipo de Solicitud" antes de mover el ticket a la etapa "%s".'
            ) % stage.name)

        description = (
            f"<p>Solicitud generada de forma automática cuando el Ticket N° {self.id} "
            f"pasó a la etapa '<strong>{stage.name}</strong>'.</p>"
        )
        if self.description:
            description += self.description

        if self.x_approval_request_id:
            self.x_approval_request_id.write({
                'category_id': category.id,
                'reason': description,
                'x_perfil_id': self.x_perfil_id.id if self.x_perfil_id else False,
                'x_departamento_id': self.x_departamento_id.id if self.x_departamento_id else False,
            })
        else:
            approval = self.env['approval.request'].sudo().create({
                'name': f"Solicito personal puesto nuevo: {self.name}",
                'category_id': category.id,
                'request_owner_id': self.env.user.id,
                'reason': description,
                'x_helpdesk_ticket_id': self.id,
                'x_perfil_id': self.x_perfil_id.id if self.x_perfil_id else False,
                'x_departamento_id': self.x_departamento_id.id if self.x_departamento_id else False,
            })
            approval.action_confirm()
            self.sudo().x_approval_request_id = approval
            self.message_post(body=Markup(_(
                '<b>Automatización Exitosa:</b> Se creó y envió la solicitud de aprobación '
                '<b>%s</b>.'
            )) % approval.name)
            approval._send_pending_approver_notification()

        self._send_pending_approval_notification()

    def _send_pending_approval_notification(self):
        self.ensure_one()
        if not self.user_id or not self.user_id.partner_id.email:
            return

        job_title = self.x_perfil_id.name if self.x_perfil_id else self.name
        requester_name = self.create_uid.name if self.create_uid else 'Solicitante'
        company_name = self.company_id.name if self.company_id else 'JE-AL ENTERPRISES INC S.A.C.'
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_url = f"{base_url}/odoo/helpdesk/{self.id}"

        subject = f"Nuevo requerimiento asignado | Ticket #{self.id} – {job_title}"
        body = f"""
            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333333; line-height: 1.5;">
                <p>Hola, {self.user_id.name}:</p>
                <br/>
                <p>Te compartimos que tienes asignado un nuevo requerimiento para el puesto de {job_title},
                correspondiente al ticket #{self.id}.</p>
                <br/>
                <p>Por favor revisa y espera las aprobaciones correspondientes para iniciar con el reclutamiento.</p>
                <p style="margin-top: 15px;">
                    <a href="{action_url}" style="background-color: #714B67; color: #ffffff; padding: 10px 18px; text-decoration: none; border-radius: 4px; display: inline-block; font-weight: bold;">Ver Ticket</a>
                </p>
                <br/>
                <p>Gracias por tu buen trabajo. Cualquier observación relevante, por favor regístrala en el sistema
                para mantener trazabilidad.</p>
                <br/>
                <p><strong>Resumen rápido:</strong></p>
                <ul style="list-style-type: disc; padding-left: 20px;">
                    <li><strong>Puesto:</strong> {job_title}</li>
                    <li><strong>Ticket:</strong> #{self.id}</li>
                    <li><strong>Solicitante:</strong> {requester_name}</li>
                    <li><strong>Empresa / Unidad:</strong> {company_name}</li>
                </ul>
            </div>
        """
        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'email_to': self.user_id.partner_id.email,
            'auto_delete': False,
        }).send()
        self.message_post(body=Markup(_(
            '<b>📧 Correo enviado</b> a <b>%s</b> (%s): "%s".'
        )) % (self.user_id.name, self.user_id.partner_id.email, subject))

    def _move_to_in_progress_stage(self):
        self.ensure_one()
        if not self.team_id:
            return
        in_progress_stage = self.env['helpdesk.stage'].search([
            ('team_ids', 'in', self.team_id.id),
            ('x_is_in_progress_stage', '=', True),
        ], limit=1)
        if in_progress_stage and self.stage_id.id != in_progress_stage.id:
            self.sudo().with_context(hrf_bypass_stage_guard=True).write({'stage_id': in_progress_stage.id})
            self.message_post(body=Markup(_(
                '<b>Automatización:</b> El ticket ha cambiado a <b>En Proceso</b> '
                'porque el reclutador registró el primer candidato para este puesto.'
            )))
