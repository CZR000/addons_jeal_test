# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountMoveRejectWizard(models.TransientModel):
    _name = 'account.move.reject.wizard'
    _description = 'Wizard para rechazar asientos contables'

    move_id = fields.Many2one(
        'account.move',
        string='Asiento Contable',
        required=True,
        readonly=True
    )

    rejection_reason = fields.Text(
        string='Motivo de Rechazo',
        required=True,
        help='Indique el motivo por el cual se rechaza este asiento'
    )

    def action_reject_move(self):
        """Rechaza el asiento con el motivo indicado"""
        self.ensure_one()
        move = self.move_id

        # Odoo 18: `user_has_groups` fue eliminado; usar `env.user.has_group`.
        if not self.env.user.has_group(
            'account_move_approval.group_account_journal_approver'
        ):
            raise UserError(_(
                "No tiene permisos para rechazar este asiento."
            ))

        if move.state != 'to_approve':
            raise UserError(_(
                "Solo puede rechazar asientos pendientes de aprobación."
            ))

        # Escribir campos de rechazo y volver a borrador
        super(type(move), move).write({
            'state': 'draft',
            'approval_state': 'rejected',
            'rejection_user_id': self.env.user.id,
            'rejection_date': fields.Datetime.now(),
            'rejection_reason': self.rejection_reason,
            # Limpiar campos de aprobación previa
            'approval_user_id': False,
            'approval_date': False,
        })

        # Completar rechazo y crear notificaciones
        move.complete_rejection(self.rejection_reason)

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
