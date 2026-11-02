# -*- coding: utf-8 -*-

from odoo import models, fields, api, Command, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    invoice_vendor_bill_id = fields.Many2one(
        comodel_name="account.move",
        string="Vendor Bill",
        check_company=True,
        store=True,
        index=True,
        tracking=False,
        help="Auto-complete from a past bill.",
    )

    state = fields.Selection(
        selection_add=[
            ('to_approve', 'Pendiente de Aprobación'),
            ('posted',)
        ],
        ondelete={'to_approve': 'set default'}
    )

    requester_user_id = fields.Many2one(
        'res.users',
        string='Solicitado por',
        readonly=True,
        copy=False,
        help='Usuario que solicitó la aprobación'
    )

    approval_user_id = fields.Many2one(
        'res.users',
        string='Aprobado por',
        readonly=True,
        copy=False
    )

    approval_date = fields.Datetime(
        string='Fecha de Aprobación',
        readonly=True,
        copy=False
    )

    approval_state = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('approved', 'Aprobado'),
            ('rejected', 'Rechazado'),
        ],
        string='Estado de Aprobación',
        readonly=True,
        copy=False,
        help='Estado del proceso de aprobación'
    )

    rejection_reason = fields.Text(
        string='Motivo de Rechazo',
        readonly=True,
        copy=False
    )

    rejection_user_id = fields.Many2one(
        'res.users',
        string='Rechazado por',
        readonly=True,
        copy=False
    )

    rejection_date = fields.Datetime(
        string='Fecha de Rechazo',
        readonly=True,
        copy=False
    )

    # -------------------------------------------------------------------------
    # Conciliación pospuesta (ver wizard/account_reconcile_wizard.py)
    # -------------------------------------------------------------------------
    # Cuando este asiento es un ajuste (write-off) generado automáticamente
    # por el wizard de conciliación de Enterprise en un diario que requiere
    # aprobación, la conciliación de la factura/pago original se pospone
    # hasta que el asiento sea aprobado (ver _complete_pending_reconciliation,
    # disparado desde action_approve).
    pending_reconcile_line_ids = fields.Many2many(
        'account.move.line',
        'account_move_approval_pending_reconcile_rel',
        'move_id', 'line_id',
        string='Líneas pendientes de conciliar',
        copy=False,
    )
    pending_reconcile_writeoff_line_id = fields.Many2one(
        'account.move.line',
        string='Línea de ajuste pendiente de conciliar',
        copy=False,
    )

    can_approve = fields.Boolean(
        compute='_compute_can_approve',
        string='Puede Aprobar'
    )

    can_reject = fields.Boolean(
        compute='_compute_can_reject',
        string='Puede Rechazar'
    )

    show_approval_button = fields.Boolean(
        compute='_compute_show_approval_button',
        string='Mostrar Botón de Aprobación'
    )

    needs_approval = fields.Boolean(
        compute='_compute_needs_approval',
        string='Requiere Aprobación',
        help='Indica si este asiento requiere pasar por flujo de aprobación'
    )

    # -------------------------------------------------------------------------
    # COMPUTED FIELDS
    # -------------------------------------------------------------------------
    # Odoo 18: el método `BaseModel.user_has_groups(spec)` fue eliminado en v18.
    # En su lugar se usa `self.env.user.has_group(xid)` para verificar un solo
    # grupo, o `self.env.user.has_groups("xid1,xid2")` para varios.

    @api.depends_context('uid')
    @api.depends('state', 'journal_id.requires_approval', 'move_type')
    def _compute_needs_approval(self):
        """Determina si el asiento necesita aprobación según el diario y el usuario"""
        is_approver = self.env.user.has_group(
            'account_move_approval.group_account_journal_approver'
        )
        for move in self:
            move.needs_approval = (
                move.move_type == 'entry'
                and move.journal_id.requires_approval
                and not is_approver  # Aprobadores pueden publicar directo
            )

    @api.depends_context('uid')
    @api.depends('state', 'journal_id.requires_approval', 'move_type')
    def _compute_show_approval_button(self):
        """
        Muestra el botón 'Solicitar Aprobación' solo si:
        - El asiento está en borrador
        - Es un asiento manual (entry)
        - El diario requiere aprobación
        - El usuario actual NO es aprobador (los aprobadores publican directo)
        """
        is_approver = self.env.user.has_group(
            'account_move_approval.group_account_journal_approver'
        )
        for move in self:
            move.show_approval_button = (
                move.state == 'draft'
                and move.move_type == 'entry'
                and move.journal_id.requires_approval
                and not is_approver
            )

    @api.depends_context('uid')
    @api.depends('state', 'create_uid')
    def _compute_can_approve(self):
        """Determina si el usuario actual puede aprobar"""
        is_approver = self.env.user.has_group(
            'account_move_approval.group_account_journal_approver'
        )
        for move in self:
            move.can_approve = (
                is_approver
                and move.state == 'to_approve'
                and move.create_uid != self.env.user  # No puede aprobar lo propio
                and move.requester_user_id != self.env.user  # Ni lo que solicitó
            )

    @api.depends_context('uid')
    @api.depends('state')
    def _compute_can_reject(self):
        """Determina si el usuario actual puede rechazar"""
        is_approver = self.env.user.has_group(
            'account_move_approval.group_account_journal_approver'
        )
        for move in self:
            move.can_reject = is_approver and move.state == 'to_approve'

    # -------------------------------------------------------------------------
    # APPROVAL FLOW ACTIONS
    # -------------------------------------------------------------------------

    def action_request_approval(self):
        """Solicita la aprobación del asiento contable"""
        self.ensure_one()

        if self.state != 'draft':
            raise UserError(_(
                "Solo puede solicitar aprobación para asientos en borrador."
            ))

        if self.move_type != 'entry':
            raise UserError(_(
                "Solo los asientos manuales requieren aprobación."
            ))

        if not self.journal_id.requires_approval:
            raise UserError(_(
                "Este diario no requiere aprobación."
            ))

        self._do_request_approval()

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _do_request_approval(self, chatter_message=None):
        """Lógica interna de solicitud de aprobación.

        Compartida entre el botón "Solicitar Aprobación" y los flujos
        automáticos (ej. asientos que el motor de conciliación intenta
        publicar directo en un diario con aprobación activada — ver
        action_post más abajo y wizard/account_reconcile_wizard.py).
        """
        self.ensure_one()

        # FIX: Limpiar actividades previas antes de crear nuevas
        # (evita duplicados si se re-solicita aprobación)
        self._close_approval_activities()

        # Limpiar campos de rechazo previo si existieran
        write_vals = {
            'state': 'to_approve',
            'approval_state': 'pending',
            'requester_user_id': self.env.user.id,
            'rejection_reason': False,
            'rejection_user_id': False,
            'rejection_date': False,
            'approval_user_id': False,
            'approval_date': False,
        }
        super(AccountMove, self).write(write_vals)

        # Programar actividades para aprobadores
        approvers = self._get_approver_users()
        if approvers:
            for approver in approvers:
                self.activity_schedule(
                    'account_move_approval.mail_act_account_move_approval',
                    user_id=approver.id,
                    summary=_('Asiento pendiente de aprobación: %s') % (
                        self.name or _('Nuevo')
                    ),
                    note=_(
                        'El asiento %s de %s requiere su aprobación.'
                    ) % (self.name or _('Nuevo'), self.env.user.name)
                )

        self.message_post(
            body=chatter_message or _(
                'Asiento enviado para aprobación por %s.'
            ) % self.env.user.name,
            subject=_('Solicitud de Aprobación')
        )

    def action_approve(self):
        """Aprueba el asiento contable y lo publica"""
        for move in self:
            # --- Validaciones ---
            if not self.env.user.has_group(
                'account_move_approval.group_account_journal_approver'
            ):
                raise UserError(_(
                    "No tiene permisos para aprobar asientos. "
                    "Debe pertenecer al grupo 'Aprobador de Asientos Contables'."
                ))

            if move.state != 'to_approve':
                raise UserError(_(
                    "Solo puede aprobar asientos en estado 'Pendiente de Aprobación'."
                ))

            if move.create_uid == self.env.user:
                raise UserError(_(
                    "No puede aprobar sus propios asientos."
                ))

            if move.requester_user_id == self.env.user:
                raise UserError(_(
                    "No puede aprobar un asiento cuya aprobación usted mismo solicitó."
                ))

            # --- FIX: Cerrar TODAS las actividades ANTES de cambiar estado ---
            move._close_approval_activities(
                feedback=_('Aprobado por %s') % self.env.user.name
            )

            # --- Paso 1: Registrar aprobación y volver a draft para action_post ---
            approval_time = fields.Datetime.now()
            super(AccountMove, move).write({
                'approval_user_id': self.env.user.id,
                'approval_date': approval_time,
                'approval_state': 'approved',
                'state': 'draft',
            })

            # --- Paso 2: Publicar con context para saltar check de aprobación ---
            try:
                move.with_context(
                    approval_posting=True
                ).action_post()
            except Exception as e:
                # Si falla la publicación, revertir al estado to_approve
                _logger.error(
                    "Error al publicar asiento %s tras aprobación: %s",
                    move.name or move.id, str(e)
                )
                super(AccountMove, move).write({
                    'approval_user_id': False,
                    'approval_date': False,
                    'approval_state': 'pending',
                    'state': 'to_approve',
                })
                raise UserError(_(
                    "Error al publicar el asiento tras la aprobación:\n\n%s\n\n"
                    "El asiento permanece pendiente de aprobación. "
                    "Corrija el problema e intente nuevamente."
                ) % str(e))

            # --- Paso 2.5: Completar conciliación pospuesta (si viene de un
            # flujo automático de conciliación, ver wizard/account_reconcile_wizard.py) ---
            if move.pending_reconcile_line_ids:
                move._complete_pending_reconciliation()

            # --- FIX: Segunda limpieza post-publicación ---
            move._close_approval_activities()

            # --- Paso 3: Mensaje en chatter ---
            approval_date_formatted = fields.Datetime.context_timestamp(
                move, approval_time
            ).strftime('%d/%m/%Y %H:%M:%S')

            move.message_post(
                body=_(
                    '✓ Asiento aprobado y publicado<br/>'
                    '<strong>Aprobado por:</strong> %s<br/>'
                    '<strong>Fecha y hora:</strong> %s'
                ) % (self.env.user.name, approval_date_formatted),
                subject=_('Asiento Aprobado')
            )

            # --- Paso 4: Mensaje directo al solicitante (opcional) ---
            move._notify_requester_by_chat(
                message=_(
                    'Su asiento <b>%s</b> ha sido <b>aprobado</b> por %s.'
                ) % (move.name, self.env.user.name)
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_reject(self):
        """Abre el wizard para rechazar el asiento con motivo"""
        self.ensure_one()

        if not self.env.user.has_group(
            'account_move_approval.group_account_journal_approver'
        ):
            raise UserError(_(
                "No tiene permisos para rechazar asientos. "
                "Debe pertenecer al grupo 'Aprobador de Asientos Contables'."
            ))

        if self.state != 'to_approve':
            raise UserError(_(
                "Solo puede rechazar asientos pendientes de aprobación."
            ))

        return {
            'name': _('Indicar Motivo de Rechazo'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
            },
        }

    def complete_rejection(self, rejection_reason):
        """Completa el rechazo del asiento y crea notificaciones"""
        self.ensure_one()

        # FIX: Cerrar actividades de aprobación con feedback
        self._close_approval_activities(
            feedback=_('Rechazado por %s. Motivo: %s') % (
                self.env.user.name, rejection_reason
            )
        )

        # Mensaje en chatter
        self.message_post(
            body=_(
                '<p><strong>✗ Asiento rechazado</strong></p>'
                '<p><strong>Rechazado por:</strong> %s</p>'
                '<p><strong>Motivo:</strong> %s</p>'
            ) % (self.env.user.name, rejection_reason),
            subject=_('Asiento Rechazado')
        )

        # Mensaje directo al solicitante (opcional)
        self._notify_requester_by_chat(
            message=_(
                'Su asiento <b>%s</b> ha sido <b>rechazado</b> por %s.'
                '<br/><b>Motivo:</b> %s'
            ) % (self.name, self.env.user.name, rejection_reason)
        )

    # -------------------------------------------------------------------------
    # OVERRIDES
    # -------------------------------------------------------------------------

    def action_post(self):
        """Override para interceptar asientos que requieren aprobación"""
        # Si viene del flujo de aprobación, saltar validación
        if self.env.context.get('approval_posting'):
            return super(AccountMove, self).action_post()

        blocked = self.browse()
        for move in self:
            if (
                move.journal_id.requires_approval
                and move.state == 'draft'
                and move.move_type == 'entry'
                and not move.approval_user_id
            ):
                # Si el usuario es aprobador, permitir publicar directo
                if self.env.user.has_group(
                    'account_move_approval.group_account_journal_approver'
                ):
                    # Registrar auto-aprobación silenciosa
                    super(AccountMove, move).write({
                        'approval_user_id': self.env.user.id,
                        'approval_date': fields.Datetime.now(),
                        'approval_state': 'approved',
                    })
                    continue

                if self.env.context.get('account_move_approval_soft_block'):
                    # Flujos automáticos (ej. wizard de conciliación bancaria):
                    # en vez de bloquear con un error que revertiría toda la
                    # transacción, el asiento queda pendiente de aprobación
                    # y simplemente no se publica.
                    move._do_request_approval(chatter_message=_(
                        'Asiento generado automáticamente durante una conciliación '
                        'y enviado para aprobación (el diario "%s" requiere aprobación).'
                    ) % move.journal_id.name)
                    blocked += move
                    continue

                raise UserError(_(
                    "Este asiento requiere aprobación antes de ser publicado.\n\n"
                    "Por favor, utilice el botón 'Solicitar Aprobación'."
                ))

        to_post = self - blocked
        if not to_post:
            return True
        return super(AccountMove, to_post).action_post()

    def _complete_pending_reconciliation(self):
        """Reconcilia las líneas que quedaron esperando este asiento (ver
        pending_reconcile_line_ids) una vez que ha sido aprobado y publicado.

        Nunca relanza la excepción: si falla, el asiento igual queda
        aprobado y publicado (eso ya ocurrió), solo se deja constancia en
        el chatter para que se reconcilie manualmente.
        """
        self.ensure_one()
        pending_lines = self.pending_reconcile_line_ids
        write_off_line = self.pending_reconcile_writeoff_line_id
        if not pending_lines or not write_off_line:
            return
        try:
            self.env['account.move.line']._reconcile_plan([[pending_lines, write_off_line]])
            self.message_post(body=_(
                'Conciliación completada automáticamente tras la aprobación de este ajuste.'
            ))
        except Exception as e:
            _logger.error(
                "No se pudo completar la conciliación pospuesta del asiento %s: %s",
                self.name or self.id, str(e)
            )
            self.message_post(body=_(
                '⚠ Este asiento fue aprobado y publicado, pero no se pudo completar '
                'automáticamente la conciliación pendiente. Debe conciliarse manualmente.'
                '<br/><strong>Motivo:</strong> %s'
            ) % str(e))
        finally:
            self.write({
                'pending_reconcile_line_ids': [Command.clear()],
                'pending_reconcile_writeoff_line_id': False,
            })

    def write(self, vals):
        """Controlar edición de asientos en aprobación"""
        allowed_fields = {
            # Campos del flujo de aprobación
            'state', 'approval_user_id', 'approval_date', 'approval_state',
            'rejection_user_id', 'rejection_date', 'rejection_reason',
            'requester_user_id',
            'pending_reconcile_line_ids', 'pending_reconcile_writeoff_line_id',
            # Campos técnicos de Odoo que sí necesitamos permitir explícitamente
            'restrict_mode_hash_table', 'posted_before', 'name', 'date',
            'auto_post', 'checked',
            # Campos de mail/actividades
            'message_main_attachment_id', 'activity_ids',
            'message_follower_ids', 'message_ids',
        }
    
        for move in self:
            if move.state == 'to_approve':
                # Ignorar campos stored-computed y related: la ORM los flushea sola
                # cuando cambian sus dependencias (p.ej. sequence_prefix depende de name).
                # No los está tocando el usuario.
                user_changing = {
                    f for f in vals
                    if f in self._fields
                    and not self._fields[f].compute
                    and not self._fields[f].related
                }
                if not user_changing.issubset(allowed_fields):
                    disallowed = user_changing - allowed_fields
                    if not self.env.user.has_group('account.group_account_manager'):
                        raise UserError(_(
                            "No puede modificar un asiento pendiente de aprobación.\n"
                            "Debe ser rechazado primero.\n\n"
                            "Campos no permitidos: %s"
                        ) % ', '.join(disallowed))
        return super(AccountMove, self).write(vals)

    def unlink(self):
        """Controlar eliminación de asientos en aprobación"""
        for move in self:
            if move.state == 'to_approve':
                raise UserError(_(
                    "No puede eliminar un asiento pendiente de aprobación.\n"
                    "Debe rechazarlo primero."
                ))
        return super(AccountMove, self).unlink()

    def button_draft(self):
        """Controlar reset a draft en asientos pendientes de aprobación"""
        for move in self:
            if move.state == 'to_approve':
                if not self.env.user.has_group(
                    'account_move_approval.group_account_journal_approver'
                ):
                    raise UserError(_(
                        "No puede restablecer a borrador un asiento pendiente "
                        "de aprobación.\n"
                        "Debe ser rechazado por un aprobador."
                    ))
                # Si el aprobador lo pasa a borrador, limpiar estado de aprobación
                super(AccountMove, move).write({
                    'approval_state': False,
                    'requester_user_id': False,
                })
                move._close_approval_activities(
                    feedback=_('Restablecido a borrador por %s') % self.env.user.name
                )
        return super(AccountMove, self).button_draft()

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _get_approver_users(self):
        """Obtiene usuarios con el grupo 'Aprobador de Asientos Contables',
        excluyendo al usuario actual"""
        approver_group = self.env.ref(
            'account_move_approval.group_account_journal_approver',
            raise_if_not_found=False
        )
        if approver_group and approver_group.users:
            return approver_group.users - self.env.user
        return self.env['res.users']

    def _close_approval_activities(self, feedback=None):
        """
        FIX v3.1: Cierra TODAS las actividades de aprobación pendientes.

        Problema original:
            action_feedback() sin sudo() solo podía cerrar las actividades
            asignadas al usuario actual. Las actividades de OTROS aprobadores
            quedaban huérfanas → spam de notificaciones.

        Solución:
            1. Buscar con sudo() TODAS las actividades del registro
            2. Dar feedback individualmente (try/except por actividad)
            3. Fallback a unlink() si action_feedback falla
            4. Limpieza adicional por summary para actividades huérfanas
        """
        activity_type = self.env.ref(
            'account_move_approval.mail_act_account_move_approval',
            raise_if_not_found=False
        )
        if not activity_type:
            _logger.warning(
                "Tipo de actividad de aprobación no encontrado (mail_act_account_move_approval)"
            )
            return

        for move in self:
            # ── Buscar TODAS las actividades de este tipo para este registro ──
            # sudo() es CLAVE: sin él, solo encontramos las del usuario actual
            activities = self.env['mail.activity'].sudo().search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', move.id),
                ('activity_type_id', '=', activity_type.id),
            ])

            if activities:
                _logger.info(
                    "Cerrando %d actividad(es) de aprobación para asiento %s (ID: %s)",
                    len(activities), move.name or 'Nuevo', move.id
                )
                if feedback:
                    # Intentar cerrar con feedback una por una
                    for activity in activities:
                        try:
                            activity.action_feedback(feedback=feedback)
                        except Exception as e:
                            _logger.warning(
                                "action_feedback falló para actividad %s "
                                "(usuario: %s): %s. Eliminando directamente.",
                                activity.id, activity.user_id.name, str(e)
                            )
                            try:
                                activity.unlink()
                            except Exception as e2:
                                _logger.error(
                                    "No se pudo eliminar actividad %s: %s",
                                    activity.id, str(e2)
                                )
                else:
                    try:
                        activities.unlink()
                    except Exception as e:
                        _logger.error(
                            "Error eliminando actividades para asiento %s: %s",
                            move.name or move.id, str(e)
                        )

            # ── Limpieza adicional: actividades huérfanas por summary ──
            orphan_activities = self.env['mail.activity'].sudo().search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', move.id),
                ('summary', 'ilike', 'aprobación'),
                ('activity_type_id', '=', activity_type.id),
            ])
            if orphan_activities:
                _logger.info(
                    "Limpiando %d actividad(es) huérfana(s) para asiento %s",
                    len(orphan_activities), move.name or 'Nuevo'
                )
                try:
                    orphan_activities.unlink()
                except Exception as e:
                    _logger.error(
                        "Error eliminando actividades huérfanas: %s", str(e)
                    )

    def _notify_requester_by_chat(self, message):
        """Envía un mensaje directo al solicitante (con manejo de errores).

        Odoo 18: el modelo `mail.channel` se renombró a `discuss.channel` en
        Odoo 17. El método `channel_get` sigue existiendo en el nuevo modelo.
        """
        self.ensure_one()
        requester = self.requester_user_id
        if not requester or requester == self.env.user or not requester.partner_id:
            return
        try:
            channel = self.env['discuss.channel'].with_context(
                active_test=False
            ).channel_get([requester.partner_id.id])
            if channel and isinstance(channel, dict) and channel.get('id'):
                ch = self.env['discuss.channel'].browse(channel['id'])
                ch.message_post(
                    body=message,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                    author_id=self.env.user.partner_id.id,
                )
            elif channel and hasattr(channel, 'id'):
                channel.message_post(
                    body=message,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                    author_id=self.env.user.partner_id.id,
                )
        except Exception as e:
            _logger.warning(
                "No se pudo enviar mensaje directo al solicitante %s: %s",
                requester.name, str(e)
            )
