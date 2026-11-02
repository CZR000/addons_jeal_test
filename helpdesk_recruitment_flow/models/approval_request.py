# -*- coding: utf-8 -*-
from markupsafe import Markup
from odoo import fields, models, _


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    x_perfil_id = fields.Many2one(
        'hr.job',
        string='Perfil',
        tracking=True,
    )
    x_departamento_id = fields.Many2one(
        'hr.department',
        string='Departamento',
        tracking=True,
    )
    x_helpdesk_ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string='Ticket de Mesa de Ayuda',
        copy=False,
        readonly=True,
    )

    def action_approve(self, approver=None):
        result = super().action_approve(approver)
        for request in self:
            if request.request_status == 'approved' and request.x_helpdesk_ticket_id:
                request.sudo()._sync_to_helpdesk_approved()
        return result

    def action_refuse(self, approver=None):
        result = super().action_refuse(approver)
        for request in self:
            if request.request_status == 'refused' and request.x_helpdesk_ticket_id:
                request.sudo()._sync_to_helpdesk_refused()
        return result

    def _get_helpdesk_approved_stage(self):
        self.ensure_one()
        ticket = self.x_helpdesk_ticket_id
        if not ticket or not ticket.team_id:
            return self.env['helpdesk.stage']
        return self.env['helpdesk.stage'].search([
            ('team_ids', 'in', ticket.team_id.id),
            ('x_is_approved_stage', '=', True),
        ], limit=1)

    def _get_helpdesk_refused_stage(self):
        self.ensure_one()
        ticket = self.x_helpdesk_ticket_id
        if not ticket or not ticket.team_id:
            return self.env['helpdesk.stage']
        return self.env['helpdesk.stage'].search([
            ('team_ids', 'in', ticket.team_id.id),
            ('x_is_refused_stage', '=', True),
        ], limit=1)

    def _sync_to_helpdesk_approved(self):
        self.ensure_one()
        ticket = self.x_helpdesk_ticket_id

        approved_stage = self._get_helpdesk_approved_stage()
        if approved_stage:
            ticket.with_context(hrf_bypass_stage_guard=True).write({
                'stage_id': approved_stage.id,
                'x_approval_date': fields.Date.today(),
            })
            ticket.message_post(body=Markup(_(
                '<b>Automatización:</b> El ticket ha cambiado a <b>Aprobado</b> '
                'debido a la validación de la solicitud <i>%s</i>.'
            )) % self.name)

        job = self.x_perfil_id or ticket.x_perfil_id
        if job:
            nuevo_numero = (job.no_of_recruitment or 0) + 1
            job.write({'no_of_recruitment': nuevo_numero})
            ticket.message_post(body=Markup(_(
                "<b>Puesto de Trabajo:</b> Se detectó que '%s' ya existe. "
                'Se incrementó la vacante a <b>%s</b> nuevos empleados a reclutar.'
            )) % (job.name, nuevo_numero))

        self._send_approval_notification_emails(ticket, 'approved')

    def _sync_to_helpdesk_refused(self):
        self.ensure_one()
        ticket = self.x_helpdesk_ticket_id

        refused_stage = self._get_helpdesk_refused_stage()
        if refused_stage:
            ticket.with_context(hrf_bypass_stage_guard=True).write({'stage_id': refused_stage.id})
            ticket.message_post(body=Markup(_(
                '<b>Automatización:</b> El ticket ha cambiado a <b>Rechazado</b> '
                'debido a la desestimación de la solicitud.'
            )))

        self._send_approval_notification_emails(ticket, 'refused')

    def _send_pending_approver_notification(self):
        self.ensure_one()
        ticket = self.x_helpdesk_ticket_id
        if not ticket:
            return

        job_title = self.x_perfil_id.name if self.x_perfil_id else ticket.name
        requester_name = ticket.create_uid.name if ticket.create_uid else 'Solicitante'
        company_name = ticket.company_id.name if ticket.company_id else 'JE-AL ENTERPRISES INC S.A.C.'

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_url = f"{base_url}/odoo/approvals/{self.id}"

        MailMail = self.env['mail.mail'].sudo()

        for approver in self.approver_ids:
            partner = approver.user_id.partner_id
            if not partner or not partner.email:
                continue
            subject = f"Nueva solicitud pendiente de revisión | Ticket #{ticket.id} – {job_title}"
            body = f"""
                <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333333; line-height: 1.5;">
                    <p>Hola, {approver.user_id.name}:</p>
                    <br/>
                    <p>Tenemos una nueva solicitud pendiente de revisión para el puesto de <strong>{job_title}</strong>,
                    vinculada al ticket #{ticket.id}.</p>
                    <br/>
                    <p>Tu validación nos ayudará a continuar el proceso correctamente y mantener el flujo del
                    requerimiento sin retrasos.</p>
                    <p>Puedes revisarlo aquí:</p>
                    <p style="margin-top: 15px;">
                        <a href="{action_url}" style="background-color: #00A09D; color: #ffffff; padding: 10px 18px; text-decoration: none; border-radius: 4px; display: inline-block; font-weight: bold;">Revisar y Aprobar</a>
                    </p>
                    <br/>
                    <p>Muchas gracias por tu apoyo.</p>
                    <br/>
                    <p><strong>Resumen rápido:</strong></p>
                    <ul style="list-style-type: disc; padding-left: 20px;">
                        <li><strong>Puesto:</strong> {job_title}</li>
                        <li><strong>Ticket:</strong> #{ticket.id}</li>
                        <li><strong>Solicitante:</strong> {requester_name}</li>
                        <li><strong>Empresa / Unidad:</strong> {company_name}</li>
                    </ul>
                </div>
            """
            MailMail.create({
                'subject': subject,
                'body_html': body,
                'email_to': partner.email,
                'auto_delete': False,
            }).send()
            ticket.message_post(body=Markup(_(
                '<b>📧 Correo enviado</b> al aprobador <b>%s</b> (%s): "%s".'
            )) % (approver.user_id.name, partner.email, subject))

    def _send_approval_notification_emails(self, ticket, status):
        self.ensure_one()

        requester_name = ticket.create_uid.name if ticket.create_uid else 'Solicitante'
        recruiter_name = ticket.user_id.name if ticket.user_id else 'Reclutador Asignado'
        job_title = self.x_perfil_id.name if self.x_perfil_id else ticket.name
        ticket_number = str(ticket.id)
        company_name = ticket.company_id.name if ticket.company_id else 'JE-AL ENTERPRISES INC S.A.C.'

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_url = f"{base_url}/odoo/helpdesk/{ticket.id}"

        MailMail = self.env['mail.mail'].sudo()

        if status == 'approved':
            if ticket.create_uid and ticket.create_uid.partner_id.email:
                asunto_sol = f"Tu requerimiento fue aprobado | Ticket #{ticket_number} – {job_title}"
                cuerpo_sol = f"""
                    <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333333; line-height: 1.5;">
                        <p>Hola, {requester_name}:</p>
                        <br/>
                        <p>Te contamos que el requerimiento del puesto de {job_title}, correspondiente al ticket #{ticket_number}, ya fue aprobado.</p>
                        <br/>
                        <p>Con esto, el proceso de reclutamiento queda formalmente iniciado y el equipo de Gestión Humana continuará con las siguientes acciones dentro del flujo.</p>
                        <br/>
                        <p>Si deseas revisar el estado del caso, puedes ingresar aquí:</p>
                        <p style="margin-top: 15px;">
                            <a href="{action_url}" style="background-color: #714B67; color: #ffffff; padding: 10px 18px; text-decoration: none; border-radius: 4px; display: inline-block; font-weight: bold;">Ver Ticket</a>
                        </p>
                        <br/>
                        <p>Gracias por el soporte y la coordinación durante esta etapa.</p>
                        <br/>
                        <p>Saludos,</p>
                        <p><strong>Equipo de Gestión Humana</strong><br/>{company_name}</p>
                    </div>
                """
                MailMail.create({
                    'subject': asunto_sol,
                    'body_html': cuerpo_sol,
                    'email_to': ticket.create_uid.partner_id.email,
                    'auto_delete': False,
                }).send()
                ticket.message_post(body=Markup(_(
                    '<b>📧 Correo enviado</b> al solicitante <b>%s</b> (%s): "%s".'
                )) % (requester_name, ticket.create_uid.partner_id.email, asunto_sol))

            if ticket.user_id and ticket.user_id.partner_id.email:
                asunto_rec = f"Nueva vacante por atender | Ticket #{ticket_number} – {job_title}"
                cuerpo_rec = f"""
                    <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333333; line-height: 1.5;">
                        <p>Hola, {recruiter_name}:</p>
                        <br/>
                        <p>Ya quedó aprobada una nueva solicitud de personal y corresponde iniciar la atención del puesto de {job_title}.</p>
                        <br/>
                        <p>Te pedimos avanzar con la creación de la vacante en Odoo y continuar con el flujo definido para el proceso.</p>
                        <br/>
                        <p><strong>Datos principales:</strong></p>
                        <ul style="list-style-type: disc; padding-left: 20px;">
                            <li><strong>Ticket de origen:</strong> #{ticket_number}</li>
                            <li><strong>Puesto:</strong> {job_title}</li>
                            <li><strong>Solicitante:</strong> {requester_name}</li>
                        </ul>
                        <br/>
                        <p>Acceso al caso:</p>
                        <p style="margin-top: 15px;">
                            <a href="{action_url}" style="background-color: #00878a; color: #ffffff; padding: 10px 18px; text-decoration: none; border-radius: 4px; display: inline-block; font-weight: bold;">Ver Caso</a>
                        </p>
                        <br/>
                        <p>Gracias por tu gestión.</p>
                        <br/>
                        <p>Saludos,</p>
                        <p><strong>Mesa de Ayuda RRHH</strong><br/>{company_name}</p>
                    </div>
                """
                MailMail.create({
                    'subject': asunto_rec,
                    'body_html': cuerpo_rec,
                    'email_to': ticket.user_id.partner_id.email,
                    'auto_delete': False,
                }).send()
                ticket.message_post(body=Markup(_(
                    '<b>📧 Correo enviado</b> al reclutador <b>%s</b> (%s): "%s".'
                )) % (recruiter_name, ticket.user_id.partner_id.email, asunto_rec))

        elif status == 'refused':
            if ticket.create_uid and ticket.create_uid.partner_id.email:
                asunto_rechazo = f"Tu requerimiento fue rechazado | Ticket #{ticket_number} – {job_title}"
                cuerpo_rechazo = f"""
                    <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333333; line-height: 1.5;">
                        <p>Hola, {requester_name}:</p>
                        <br/>
                        <p>Te informamos que el requerimiento del puesto de {job_title}, correspondiente al ticket #{ticket_number}, ha sido <b>rechazado</b> por el aprobador asignado.</p>
                        <br/>
                        <p>Debido a esto, el proceso de reclutamiento no será iniciado y el caso ha sido derivado a la etapa de cierre en la Mesa de Ayuda.</p>
                        <br/>
                        <p>Si deseas revisar el estado o los comentarios del caso, puedes ingresar aquí:</p>
                        <p style="margin-top: 15px;">
                            <a href="{action_url}" style="background-color: #dc3545; color: #ffffff; padding: 10px 18px; text-decoration: none; border-radius: 4px; display: inline-block; font-weight: bold;">Ver Detalles</a>
                        </p>
                        <br/>
                        <p>Agradecemos tu comprensión durante este proceso.</p>
                        <br/>
                        <p>Saludos,</p>
                        <p><strong>Equipo de Gestión Humana</strong><br/>{company_name}</p>
                    </div>
                """
                MailMail.create({
                    'subject': asunto_rechazo,
                    'body_html': cuerpo_rechazo,
                    'email_to': ticket.create_uid.partner_id.email,
                    'auto_delete': False,
                }).send()
                ticket.message_post(body=Markup(_(
                    '<b>📧 Correo enviado</b> al solicitante <b>%s</b> (%s): "%s".'
                )) % (requester_name, ticket.create_uid.partner_id.email, asunto_rechazo))
