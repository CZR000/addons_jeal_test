import logging
from markupsafe import Markup, escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # ------------------------------------------------------------------
    # Disbursement request fields
    # ------------------------------------------------------------------
    is_disbursement_request = fields.Boolean(
        string='Es solicitud de desembolso',
        default=False,
        copy=False,
        index=True,
        help='Marca este pago como una solicitud de desembolso del módulo de gastos.',
    )
    disbursement_state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('pending', 'Pendiente de aprobación'),
            ('approved', 'Aprobado'),
            ('rejected', 'Rechazado'),
        ],
        string='Estado desembolso',
        default='draft',
        copy=False,
        readonly=True,
        tracking=True,
        help='Estado del flujo de aprobación de la solicitud de desembolso.',
    )
    disbursement_requester_id = fields.Many2one(
        'res.users',
        string='Solicitado por',
        readonly=True,
        copy=False,
    )
    disbursement_approver_id = fields.Many2one(
        'res.users',
        string='Aprobado por',
        readonly=True,
        copy=False,
    )
    disbursement_approval_date = fields.Datetime(
        string='Fecha de aprobación',
        readonly=True,
        copy=False,
    )
    disbursement_rejection_reason = fields.Text(
        string='Motivo de rechazo',
        readonly=True,
        copy=False,
    )
    disbursement_rejection_user_id = fields.Many2one(
        'res.users',
        string='Rechazado por',
        readonly=True,
        copy=False,
    )
    disbursement_rejection_date = fields.Datetime(
        string='Fecha de rechazo',
        readonly=True,
        copy=False,
    )

    # Computed helpers
    can_request_disbursement = fields.Boolean(
        string='Puede solicitar desembolso',
        compute='_compute_disbursement_buttons',
        store=False,
    )
    can_approve_disbursement = fields.Boolean(
        string='Puede aprobar desembolso',
        compute='_compute_disbursement_buttons',
        store=False,
    )

    # ------------------------------------------------------------------
    # Compute helpers
    # ------------------------------------------------------------------
    @api.depends_context('uid')
    @api.depends('is_disbursement_request', 'disbursement_state', 'state')
    def _compute_disbursement_buttons(self):
        is_approver = self.env.user.has_group(
            'hr_expense_cust.group_hr_expense_sheet_approver'
        )
        for pay in self:
            pay.can_request_disbursement = (
                pay.is_disbursement_request
                and pay.disbursement_state == 'draft'
                and pay.state == 'draft'
            )
            pay.can_approve_disbursement = (
                is_approver
                and pay.is_disbursement_request
                and pay.disbursement_state == 'pending'
            )

    # ------------------------------------------------------------------
    # Override _compute_destination_account_id: don't overwrite manually
    # set destination for disbursement requests
    # ------------------------------------------------------------------
    @api.depends('journal_id', 'partner_id', 'partner_type', 'is_disbursement_request')
    def _compute_destination_account_id(self):
        """
        For disbursement requests that already have destination_account_id set,
        skip recomputation to preserve the manually chosen account.
        """
        disbursements_with_account = self.filtered(
            lambda p: p.is_disbursement_request and p.destination_account_id
        )
        others = self - disbursements_with_account
        if others:
            super(AccountPayment, others)._compute_destination_account_id()
        # disbursements_with_account: leave their destination_account_id unchanged

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_request_disbursement(self):
        """Solicitar aprobación del desembolso."""
        self.ensure_one()
        if not self.is_disbursement_request:
            raise UserError(_('Este pago no es una solicitud de desembolso.'))
        if self.disbursement_state != 'draft':
            raise UserError(_(
                'La solicitud de desembolso ya fue enviada o procesada.'
            ))

        approvers = self._get_disbursement_approvers()
        if not approvers:
            raise UserError(_(
                'No hay usuarios con el permiso "Aprobador de informe de gastos" '
                'configurados. Por favor, asigne ese perfil a al menos un usuario '
                'en Ajustes → Usuarios.'
            ))

        self.write({
            'disbursement_state': 'pending',
            'disbursement_requester_id': self.env.user.id,
        })

        # Schedule activity for each approver
        for approver in approvers:
            self.activity_schedule(
                'hr_expense_cust.mail_act_disbursement_approval',
                user_id=approver.id,
                summary=_('Solicitud de desembolso: %s') % (self.name or '/'),
                note=Markup(_(
                    '<p>El usuario <b>%(user)s</b> ha solicitado un desembolso '
                    'por <b>%(amount)s %(currency)s</b>.</p>'
                    '<p><b>Memo:</b> %(memo)s</p>'
                    '<p>Por favor revise y apruebe o rechace la solicitud.</p>'
                )) % {
                    'user': escape(self.env.user.name),
                    'amount': self.amount,
                    'currency': escape(self.currency_id.name),
                    'memo': escape(self.memo or ''),
                },
            )

        # Chatter message
        self.message_post(
            body=Markup(_(
                '<p>⏳ Solicitud de desembolso enviada para aprobación por '
                '<b>%(user)s</b>.</p>'
            )) % {'user': escape(self.env.user.name)},
            subject=_('Solicitud de desembolso enviada'),
        )

        # Chat notification to approvers
        for approver in approvers:
            self._notify_disbursement_by_chat(
                approver,
                Markup(_(
                    '<p>Nueva solicitud de desembolso de <b>%(user)s</b> '
                    'por <b>%(amount)s %(currency)s</b> pendiente de tu aprobación.</p>'
                )) % {
                    'user': escape(self.env.user.name),
                    'amount': self.amount,
                    'currency': escape(self.currency_id.name),
                },
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Solicitud enviada'),
                'message': _(
                    'La solicitud de desembolso fue enviada a los aprobadores.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_approve_disbursement(self):
        """Aprobar la solicitud de desembolso (solo aprobadores)."""
        self.ensure_one()
        if not self.env.user.has_group('hr_expense_cust.group_hr_expense_sheet_approver'):
            raise UserError(_(
                'Solo los usuarios con el perfil "Aprobador de informe de gastos" '
                'pueden aprobar solicitudes de desembolso.'
            ))
        if self.disbursement_state != 'pending':
            raise UserError(_(
                'Esta solicitud no está pendiente de aprobación.'
            ))

        # Close pending activities
        self._close_disbursement_activities(
            feedback=_('Aprobado por %s') % self.env.user.name
        )

        self.write({
            'disbursement_state': 'approved',
            'disbursement_approver_id': self.env.user.id,
            'disbursement_approval_date': fields.Datetime.now(),
        })

        # Auto-validate the payment (generates journal entries)
        try:
            self.action_post()
        except Exception as e:
            _logger.error(
                'Error al validar pago de desembolso %s: %s', self.name, str(e)
            )
            raise UserError(_(
                'La solicitud fue aprobada pero no se pudo validar automáticamente '
                'el pago.\n\nMotivo: %s\n\nVerifique la configuración del diario.'
            ) % str(e)) from e

        # Chatter message
        self.message_post(
            body=Markup(_(
                '<p>✅ Solicitud de desembolso <b>aprobada</b> por <b>%(approver)s</b>. '
                'El pago ha sido validado y los asientos contables generados.</p>'
            )) % {'approver': escape(self.env.user.name)},
            subject=_('Solicitud de desembolso aprobada'),
        )

        # Notify requester
        requester = self.disbursement_requester_id
        if requester and requester != self.env.user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=requester.id,
                summary=_('Desembolso aprobado: %s') % (self.name or '/'),
                note=Markup(_(
                    '<p>Tu solicitud de desembolso <b>%(name)s</b> fue '
                    '<b>aprobada</b> por <b>%(approver)s</b>.</p>'
                )) % {
                    'name': escape(self.name or '/'),
                    'approver': escape(self.env.user.name),
                },
            )
            self._notify_disbursement_by_chat(
                requester,
                Markup(_(
                    '<p>Tu solicitud de desembolso <b>%(name)s</b> fue '
                    '<b>aprobada</b> por %(approver)s.</p>'
                )) % {
                    'name': escape(self.name or '/'),
                    'approver': escape(self.env.user.name),
                },
            )

    def action_reject_disbursement(self):
        """Rechazar la solicitud de desembolso (abre wizard)."""
        self.ensure_one()
        if not self.env.user.has_group('hr_expense_cust.group_hr_expense_sheet_approver'):
            raise UserError(_(
                'Solo los usuarios con el perfil "Aprobador de informe de gastos" '
                'pueden rechazar solicitudes de desembolso.'
            ))
        if self.disbursement_state != 'pending':
            raise UserError(_(
                'Esta solicitud no está pendiente de aprobación.'
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rechazar solicitud de desembolso'),
            'res_model': 'expense.disbursement.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payment_id': self.id,
                'dialog_size': 'medium',
            },
        }

    def complete_disbursement_rejection(self, reason):
        """Completar el rechazo (llamado desde el wizard)."""
        self.ensure_one()
        self._close_disbursement_activities(
            feedback=_('Rechazado por %(user)s: %(reason)s') % {
                'user': self.env.user.name,
                'reason': reason,
            }
        )
        self.write({
            'disbursement_state': 'rejected',
            'disbursement_rejection_reason': reason,
            'disbursement_rejection_user_id': self.env.user.id,
            'disbursement_rejection_date': fields.Datetime.now(),
        })

        self.message_post(
            body=Markup(_(
                '<p>❌ Solicitud de desembolso <b>rechazada</b> por <b>%(user)s</b>.</p>'
                '<p><b>Motivo:</b> %(reason)s</p>'
            )) % {'user': escape(self.env.user.name), 'reason': escape(reason)},
            subject=_('Solicitud de desembolso rechazada'),
        )

        requester = self.disbursement_requester_id
        if requester and requester != self.env.user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=requester.id,
                summary=_('Desembolso rechazado: %s') % (self.name or '/'),
                note=Markup(_(
                    '<p>Tu solicitud de desembolso <b>%(name)s</b> fue '
                    '<b>rechazada</b> por <b>%(user)s</b>.</p>'
                    '<p><b>Motivo:</b> %(reason)s</p>'
                )) % {
                    'name': escape(self.name or '/'),
                    'user': escape(self.env.user.name),
                    'reason': escape(reason),
                },
            )
            self._notify_disbursement_by_chat(
                requester,
                Markup(_(
                    '<p>Tu solicitud de desembolso <b>%(name)s</b> fue '
                    '<b>rechazada</b> por %(user)s.</p>'
                    '<p><b>Motivo:</b> %(reason)s</p>'
                )) % {
                    'name': escape(self.name or '/'),
                    'user': escape(self.env.user.name),
                    'reason': escape(reason),
                },
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_disbursement_approvers(self):
        """Retorna usuarios activos con el perfil aprobador, excepto el solicitante."""
        group = self.env.ref(
            'hr_expense_cust.group_hr_expense_sheet_approver',
            raise_if_not_found=False,
        )
        if not group:
            return self.env['res.users']
        return group.users.filtered(
            lambda u: u.active and u.id != self.env.user.id
        )

    def _close_disbursement_activities(self, feedback=None):
        """Cierra actividades pendientes de aprobación de desembolso."""
        activity_type = self.env.ref(
            'hr_expense_cust.mail_act_disbursement_approval',
            raise_if_not_found=False,
        )
        if not activity_type:
            return
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'account.payment'),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', activity_type.id),
        ])
        if activities:
            if feedback:
                activities.action_feedback(feedback=feedback)
            else:
                activities.unlink()

    def _notify_disbursement_by_chat(self, target_user, message):
        """Envía mensaje directo al usuario (falla silenciosamente)."""
        if not target_user or target_user == self.env.user or not target_user.partner_id:
            return
        try:
            channel = self.env['discuss.channel'].with_context(
                active_test=False
            ).channel_get([target_user.partner_id.id])
            channel.message_post(
                body=message,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=self.env.user.partner_id.id,
            )
        except Exception as exc:
            _logger.warning(
                'No se pudo enviar mensaje de desembolso: %s', str(exc)
            )
