import logging
from markupsafe import Markup, escape
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ir.config_parameter keys
_PARAM_MAX_PCT_NO_APPROVAL = 'sale_discount_approval.max_discount_no_approval'
_PARAM_MAX_PCT_WITH_APPROVAL = 'sale_discount_approval.max_discount_with_approval'
_PARAM_MAX_FIXED_NO_APPROVAL = 'sale_discount_approval.max_discount_fixed_no_approval'
_PARAM_MAX_FIXED_WITH_APPROVAL = 'sale_discount_approval.max_discount_fixed_with_approval'

# Default values (used when parameters are not yet set)
_DEFAULT_MAX_PCT_NO_APPROVAL = 10.0
_DEFAULT_MAX_FIXED_NO_APPROVAL = 0.0


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # -------------------------------------------------------------------------
    # Approval state fields
    # -------------------------------------------------------------------------
    discount_approval_state = fields.Selection(
        selection=[
            ('not_required', 'No requerida'),
            ('pending', 'Pendiente de aprobación'),
            ('approved', 'Aprobada'),
            ('rejected', 'Rechazada'),
        ],
        string='Estado aprobación descuento',
        default='not_required',
        copy=False,
        readonly=True,
        tracking=True,
    )
    discount_requester_id = fields.Many2one(
        'res.users',
        string='Aprobación solicitada por',
        readonly=True,
        copy=False,
    )
    discount_approver_id = fields.Many2one(
        'res.users',
        string='Aprobado por',
        readonly=True,
        copy=False,
    )
    discount_approval_date = fields.Datetime(
        string='Fecha de aprobación',
        readonly=True,
        copy=False,
    )
    discount_rejection_reason = fields.Text(
        string='Motivo de rechazo',
        readonly=True,
        copy=False,
    )
    discount_rejection_user_id = fields.Many2one(
        'res.users',
        string='Rechazado por',
        readonly=True,
        copy=False,
    )
    discount_rejection_date = fields.Datetime(
        string='Fecha de rechazo',
        readonly=True,
        copy=False,
    )

    # -------------------------------------------------------------------------
    # Computed helpers for UI visibility
    # -------------------------------------------------------------------------
    requires_discount_approval = fields.Boolean(
        string='Requiere aprobación de descuento',
        compute='_compute_requires_discount_approval',
        store=False,
    )
    can_approve_discount = fields.Boolean(
        string='Puede aprobar/rechazar descuento',
        compute='_compute_can_approve_discount',
        store=False,
    )
    show_request_approval_button = fields.Boolean(
        string='Mostrar botón solicitar aprobación',
        compute='_compute_show_request_approval_button',
        store=False,
    )

    # -------------------------------------------------------------------------
    # Helpers: read thresholds from ir.config_parameter
    # -------------------------------------------------------------------------
    def _get_discount_thresholds(self):
        """Return a dict with the four discount thresholds from Settings."""
        get_param = self.env['ir.config_parameter'].sudo().get_param

        def _float(key, default):
            try:
                return float(get_param(key, default))
            except (TypeError, ValueError):
                return float(default)

        return {
            'max_pct_no_approval': _float(_PARAM_MAX_PCT_NO_APPROVAL, _DEFAULT_MAX_PCT_NO_APPROVAL),
            'max_pct_with_approval': _float(_PARAM_MAX_PCT_WITH_APPROVAL, 0.0),
            'max_fixed_no_approval': _float(_PARAM_MAX_FIXED_NO_APPROVAL, _DEFAULT_MAX_FIXED_NO_APPROVAL),
            'max_fixed_with_approval': _float(_PARAM_MAX_FIXED_WITH_APPROVAL, 0.0),
        }

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------
    @api.depends_context('uid')
    @api.depends('order_line.discount', 'discount_approval_state')
    def _compute_requires_discount_approval(self):
        # Sales Managers can always apply discounts without needing approval
        if self.env.user.is_sales_manager:
            for order in self:
                order.requires_discount_approval = False
            return
        thresholds = self._get_discount_thresholds()
        for order in self:
            if order.discount_approval_state == 'approved':
                order.requires_discount_approval = False
            else:
                order.requires_discount_approval = order._check_discount_exceeds_limit(thresholds)

    @api.depends_context('uid')
    @api.depends('discount_approval_state', 'discount_requester_id')
    def _compute_can_approve_discount(self):
        is_manager = self.env.user.is_sales_manager
        for order in self:
            order.can_approve_discount = (
                is_manager
                and order.discount_approval_state == 'pending'
                and order.discount_requester_id != self.env.user
            )

    @api.depends('requires_discount_approval', 'discount_approval_state')
    def _compute_show_request_approval_button(self):
        for order in self:
            order.show_request_approval_button = (
                order.requires_discount_approval
                and order.discount_approval_state in ('not_required', 'rejected')
                and order.state in ('draft', 'sent')
            )

    # -------------------------------------------------------------------------
    # Business logic helpers
    # -------------------------------------------------------------------------
    def _check_discount_exceeds_limit(self, thresholds=None):
        """Return True if any line has a discount exceeding the no-approval limit."""
        if thresholds is None:
            thresholds = self._get_discount_thresholds()
        line_model_fields = self.env['sale.order.line']._fields
        has_fixed_discount_field = 'discount_fixed' in line_model_fields
        max_pct = thresholds['max_pct_no_approval']
        max_fixed = thresholds['max_fixed_no_approval']
        for line in self.order_line:
            if line.discount and line.discount > max_pct:
                return True
            if has_fixed_discount_field and max_fixed > 0:
                fixed = getattr(line, 'discount_fixed', 0.0) or 0.0
                if fixed > max_fixed:
                    return True
        return False

    def _has_discount_changes_in_commands(self, line_commands):
        """Return True if x2many commands modify discount fields."""
        discount_fields = {'discount', 'discount_fixed'}
        for command in line_commands:
            if not command:
                continue
            cmd_type = command[0]
            # 0 = CREATE, 1 = UPDATE
            if cmd_type in (0, 1):
                line_vals = command[2] if len(command) > 2 else {}
                if discount_fields.intersection(set(line_vals.keys())):
                    return True
        return False

    def _get_sales_manager_users(self):
        """Return active Sales Manager users excluding the current user."""
        return self.env['res.users'].search([
            ('is_sales_manager', '=', True),
            ('id', '!=', self.env.user.id),
            ('active', '=', True),
        ])

    def _auto_request_discount_approval(self, thresholds, managers):
        """Automatically transition to pending and notify managers."""
        self.ensure_one()
        # Set pending state (skip_discount_check avoids infinite recursion)
        self.with_context(skip_discount_check=True).write({
            'discount_approval_state': 'pending',
            'discount_requester_id': self.env.user.id,
            'discount_approver_id': False,
            'discount_approval_date': False,
            'discount_rejection_reason': False,
            'discount_rejection_user_id': False,
            'discount_rejection_date': False,
        })
        # Schedule activity for each manager
        order_name = self.name or _('Nueva cotización')
        limit_pct = thresholds['max_pct_no_approval']
        for manager in managers:
            self.activity_schedule(
                'sale_discount_approval.mail_act_sale_discount_approval',
                user_id=manager.id,
                summary=_('Aprobación de descuento: %s') % order_name,
                note=Markup(_(
                    '<p>La cotización <b>%(order)s</b> del cliente <b>%(partner)s</b> '
                    'contiene descuentos que superan el límite permitido sin autorización '
                    '(<b>%(limit).2f%%</b>) y requiere su aprobación.</p>'
                    '<p>Solicitado por: <b>%(user)s</b></p>'
                )) % {
                    'order': escape(order_name),
                    'partner': escape(self.partner_id.name or ''),
                    'limit': limit_pct,
                    'user': escape(self.env.user.name),
                },
            )
        # Chatter message
        self.message_post(
            body=Markup(_(
                '<p>⚠ Se solicitó aprobación de descuento automáticamente.<br/>'
                'Solicitado por: <b>%(user)s</b><br/>'
                'Los Gerentes de Ventas han sido notificados mediante actividades.</p>'
            )) % {'user': escape(self.env.user.name)},
            subject=_('Aprobación de descuento solicitada'),
        )

    def _close_discount_approval_activities(self, feedback=None):
        """Close pending discount approval activities with optional feedback."""
        activity_type = self.env.ref(
            'sale_discount_approval.mail_act_sale_discount_approval',
            raise_if_not_found=False,
        )
        if not activity_type:
            return
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', activity_type.id),
        ])
        if activities:
            if feedback:
                activities.action_feedback(feedback=feedback)
            else:
                activities.unlink()

    def _notify_user_by_chat(self, target_user, message):
        """Send a direct chat message to the target user (fails silently)."""
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
            _logger.warning('Could not send discount approval chat message: %s', str(exc))

    # -------------------------------------------------------------------------
    # ORM overrides
    # -------------------------------------------------------------------------
    def write(self, vals):
        if not self.env.context.get('skip_discount_check') and not self.env.user.is_sales_manager:
            for order in self:
                # Block discount field changes while approval is pending (non-managers only)
                if order.discount_approval_state == 'pending':
                    if order._has_discount_changes_in_commands(
                        vals.get('order_line', [])
                    ):
                        raise UserError(
                            _('No puede modificar los descuentos mientras la aprobación '
                              'del Gerente de Ventas está pendiente.\n\n'
                              'Espere a que el Gerente de Ventas apruebe o rechace '
                              'el descuento actual.')
                        )

        result = super().write(vals)

        # Post-write: re-evaluate discount limits (Sales Managers are exempt)
        if not self.env.context.get('skip_discount_check') and not self.env.user.is_sales_manager:
            thresholds = self._get_discount_thresholds()
            line_commands = vals.get('order_line', [])
            for order in self:
                state = order.discount_approval_state

                if state in ('not_required', 'rejected'):
                    if order._check_discount_exceeds_limit(thresholds):
                        managers = order._get_sales_manager_users()
                        if not managers:
                            raise UserError(
                                _('No hay usuarios configurados como Gerente de Ventas.\n\n'
                                  'No es posible solicitar aprobación de descuento porque '
                                  'no existe ningún Gerente de Ventas configurado en el sistema.\n'
                                  'Por favor, marque al menos un usuario como "Gerente de Ventas" '
                                  'en Ajustes → Usuarios.')
                            )
                        order._auto_request_discount_approval(thresholds, managers)
                    elif state == 'rejected':
                        # Discounts now within limit after rejection — reset
                        order.with_context(skip_discount_check=True).write({
                            'discount_approval_state': 'not_required',
                        })

                elif state == 'approved':
                    # Re-check only when discount fields actually changed
                    if order._has_discount_changes_in_commands(line_commands):
                        if order._check_discount_exceeds_limit(thresholds):
                            # Discount modified to exceed limit again → new approval cycle
                            managers = order._get_sales_manager_users()
                            if not managers:
                                raise UserError(
                                    _('No hay usuarios configurados como Gerente de Ventas.\n\n'
                                      'Por favor, marque al menos un usuario como "Gerente de Ventas" '
                                      'en Ajustes → Usuarios.')
                                )
                            order.with_context(skip_discount_check=True).write({
                                'discount_approval_state': 'not_required',
                            })
                            order._auto_request_discount_approval(thresholds, managers)
                        else:
                            # Discount lowered to within limit — approval no longer needed
                            order.with_context(skip_discount_check=True).write({
                                'discount_approval_state': 'not_required',
                            })

        return result

    def action_confirm(self):
        """Block order confirmation when discount approval is pending or required.
        Sales Managers are exempt and can confirm directly."""
        if not self.env.user.is_sales_manager:
            thresholds = self._get_discount_thresholds()
            for order in self:
                if order.discount_approval_state == 'pending':
                    raise UserError(
                        _('La cotización "%s" tiene descuentos pendientes de aprobación.\n\n'
                          'El Gerente de Ventas debe aprobar los descuentos antes de '
                          'confirmar el pedido.')
                        % order.name
                    )
                if order._check_discount_exceeds_limit(thresholds):
                    if order.discount_approval_state != 'approved':
                        raise UserError(
                            _('La cotización "%s" contiene descuentos que superan el límite '
                              'sin autorización (%.2f%%).\n\n'
                              'El Gerente de Ventas debe aprobar los descuentos antes de '
                              'confirmar el pedido.')
                            % (order.name, thresholds['max_pct_no_approval'])
                        )
        return super().action_confirm()

    # -------------------------------------------------------------------------
    # Button actions
    # -------------------------------------------------------------------------
    def action_request_discount_approval(self):
        """Manually request discount approval (button for 'not_required'/'rejected' state)."""
        self.ensure_one()
        thresholds = self._get_discount_thresholds()
        if not self._check_discount_exceeds_limit(thresholds):
            raise UserError(
                _('Los descuentos en esta cotización están dentro del límite permitido. '
                  'No se requiere aprobación.')
            )
        managers = self._get_sales_manager_users()
        if not managers:
            raise UserError(
                _('No hay usuarios configurados como Gerente de Ventas.\n\n'
                  'Por favor, marque al menos un usuario como "Gerente de Ventas" '
                  'en Ajustes → Usuarios.')
            )
        self._auto_request_discount_approval(thresholds, managers)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Aprobación solicitada'),
                'message': _(
                    'Se ha enviado una solicitud de aprobación de descuento '
                    'al Gerente de Ventas.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_approve_discount(self):
        """Approve the discount (Sales Manager only)."""
        self.ensure_one()
        if not self.env.user.is_sales_manager:
            raise UserError(_('Solo el Gerente de Ventas puede aprobar descuentos.'))
        if self.discount_approval_state != 'pending':
            raise UserError(
                _('Esta cotización no está pendiente de aprobación de descuento.')
            )
        # Close pending activities with feedback
        self._close_discount_approval_activities(
            feedback=_('Aprobado por %s') % self.env.user.name
        )
        # Update approval state
        self.with_context(skip_discount_check=True).write({
            'discount_approval_state': 'approved',
            'discount_approver_id': self.env.user.id,
            'discount_approval_date': fields.Datetime.now(),
        })
        # Notify requester via activity
        requester = self.discount_requester_id
        if requester and requester != self.env.user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=requester.id,
                summary=_('Descuento aprobado: %s') % self.name,
                note=Markup(_(
                    '<p>El descuento en la cotización <b>%(order)s</b> ha sido '
                    '<b>aprobado</b> por <b>%(manager)s</b>.</p>'
                    '<p>Ya puede confirmar el pedido.</p>'
                )) % {'order': escape(self.name), 'manager': escape(self.env.user.name)},
            )
        # Chatter message
        self.message_post(
            body=Markup(_(
                '<p>✓ Descuento aprobado por <b>%(manager)s</b>.</p>'
            )) % {'manager': escape(self.env.user.name)},
            subject=_('Descuento Aprobado'),
        )
        # Chat notification to requester
        self._notify_user_by_chat(
            requester,
            Markup(_(
                '<p>El descuento en la cotización <b>%(order)s</b> ha sido '
                '<b>aprobado</b> por %(manager)s. Ya puede confirmar el pedido.</p>'
            )) % {'order': escape(self.name), 'manager': escape(self.env.user.name)},
        )

    def action_reject_discount(self):
        """Open rejection wizard (Sales Manager only)."""
        self.ensure_one()
        if not self.env.user.is_sales_manager:
            raise UserError(_('Solo el Gerente de Ventas puede rechazar descuentos.'))
        if self.discount_approval_state != 'pending':
            raise UserError(
                _('Esta cotización no está pendiente de aprobación de descuento.')
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rechazar Descuento'),
            'res_model': 'sale.discount.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'dialog_size': 'medium',
            },
        }

    def complete_discount_rejection(self, reason):
        """Complete the rejection process (called from the rejection wizard)."""
        self.ensure_one()
        # Close pending activities with feedback
        self._close_discount_approval_activities(
            feedback=_('Rechazado por %(user)s: %(reason)s') % {
                'user': self.env.user.name,
                'reason': reason,
            }
        )
        # Update state
        self.with_context(skip_discount_check=True).write({
            'discount_approval_state': 'rejected',
            'discount_rejection_reason': reason,
            'discount_rejection_user_id': self.env.user.id,
            'discount_rejection_date': fields.Datetime.now(),
        })
        # Notify requester via activity
        requester = self.discount_requester_id
        if requester and requester != self.env.user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=requester.id,
                summary=_('Descuento rechazado: %s') % self.name,
                note=Markup(_(
                    '<p>El descuento en la cotización <b>%(order)s</b> ha sido '
                    '<b>rechazado</b> por <b>%(manager)s</b>.</p>'
                    '<p><b>Motivo:</b> %(reason)s</p>'
                    '<p>Por favor, ajuste los descuentos y vuelva a solicitar autorización.</p>'
                )) % {
                    'order': escape(self.name),
                    'manager': escape(self.env.user.name),
                    'reason': escape(reason),
                },
            )
        # Chatter message
        self.message_post(
            body=Markup(_(
                '<p>✗ Descuento rechazado por <b>%(manager)s</b>.<br/>'
                '<b>Motivo:</b> %(reason)s</p>'
            )) % {'manager': escape(self.env.user.name), 'reason': escape(reason)},
            subject=_('Descuento Rechazado'),
        )
        # Chat notification to requester
        self._notify_user_by_chat(
            requester,
            Markup(_(
                '<p>El descuento en la cotización <b>%(order)s</b> ha sido '
                '<b>rechazado</b> por %(manager)s.</p>'
                '<p><b>Motivo:</b> %(reason)s</p>'
                '<p>Por favor, ajuste los descuentos y solicite nueva autorización.</p>'
            )) % {
                'order': escape(self.name),
                'manager': escape(self.env.user.name),
                'reason': escape(reason),
            },
        )
