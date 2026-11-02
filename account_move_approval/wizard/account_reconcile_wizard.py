# -*- coding: utf-8 -*-
import logging

from odoo import models, Command, _

_logger = logging.getLogger(__name__)


class AccountReconcileWizard(models.TransientModel):
    _inherit = 'account.reconcile.wizard'

    def reconcile(self):
        """
        Override: si el ajuste ("write-off", ej. redondeo) que arma este
        wizard cae en un diario que requiere aprobación (account_move_approval),
        publicarlo y conciliar de inmediato dejaría la factura/pago "cerrados"
        antes de que el ajuste esté realmente aprobado. En su lugar, el
        asiento se guarda como Pendiente de Aprobación y la conciliación de
        esas líneas se pospone hasta que un aprobador lo apruebe (ver
        account.move._complete_pending_reconciliation, disparado desde
        action_approve).

        Nota de mantenimiento: cuando hay write-off, este método reproduce
        la lógica de account_accountant.wizard.account_reconcile_wizard
        .reconcile() con un único punto de inserción (marcado abajo). Si
        Enterprise cambia esa lógica en una actualización de Odoo, hay que
        re-sincronizar este override.
        """
        self.ensure_one()
        do_write_off = self.edit_mode or (self.is_write_off_required and not self.allow_partials)

        if not do_write_off:
            # Sin ajuste de por medio: nada que interceptar, camino normal.
            return super().reconcile()

        move_lines_to_reconcile = self.move_line_ids._origin
        do_transfer = self.is_transfer_required

        if do_transfer:
            transfer_move = self.create_transfer()
            lines_to_transfer = move_lines_to_reconcile \
                .filtered(lambda line: line.account_id == self.transfer_from_account_id)
            transfer_line_from = transfer_move.line_ids \
                .filtered(lambda line: line.account_id == self.transfer_from_account_id)
            transfer_line_to = transfer_move.line_ids \
                .filtered(lambda line: line.account_id == self.reco_account_id)
            (lines_to_transfer + transfer_line_from).reconcile()
            move_lines_to_reconcile = move_lines_to_reconcile - lines_to_transfer + transfer_line_to

        # ── Punto de inserción: crear el write-off con el chequeo de aprobación activado ──
        write_off_move = self.with_context(
            account_move_approval_soft_block=True
        ).create_write_off()
        write_off_line_to_reconcile = write_off_move.line_ids[0]

        if write_off_move.state != 'posted':
            # Quedó pendiente de aprobación: no reconciliar todavía.
            write_off_move.write({
                'pending_reconcile_line_ids': [Command.set(move_lines_to_reconcile.ids)],
                'pending_reconcile_writeoff_line_id': write_off_line_to_reconcile.id,
            })
            _logger.info(
                "Conciliación pospuesta: asiento de ajuste %s (diario %s) quedó "
                "pendiente de aprobación. Líneas en espera: %s",
                write_off_move.name or write_off_move.id,
                write_off_move.journal_id.name,
                move_lines_to_reconcile.ids,
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Ajuste pendiente de aprobación'),
                    'message': _(
                        'El ajuste "%s" requiere aprobación (diario "%s"). '
                        'Quedó guardado como pendiente y la conciliación se '
                        'completará automáticamente cuando sea aprobado.'
                    ) % (write_off_move.name or _('Nuevo'), write_off_move.journal_id.name),
                    'type': 'warning',
                    'sticky': True,
                },
            }
        # ── Fin del punto de inserción ──

        move_lines_to_reconcile += write_off_line_to_reconcile
        amls_plan = [[move_lines_to_reconcile, write_off_line_to_reconcile]]

        self.env['account.move.line']._reconcile_plan(amls_plan)
        return move_lines_to_reconcile if not do_transfer else (move_lines_to_reconcile + transfer_move.line_ids)

    def reconcile_open(self):
        result = self.reconcile()
        if isinstance(result, dict):
            # El reconcile() quedó pendiente de aprobación: devolver la
            # notificación tal cual, no hay vista de conciliación que abrir.
            return result
        return result.open_reconcile_view()
