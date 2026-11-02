# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, AccessError


class AccountMove(models.Model):
    _inherit = "account.move"

    active = fields.Boolean(
        string="Activo",
        default=True,
        tracking=True,
        help="Desmárquelo para archivar el asiento en lugar de eliminarlo.",
    )

    # def _archive_moves(self):
    #     """
    #     El registro se archiva de forma segura en lugar de eliminarse.
    #     """
    #     self.write({"active": False})
    #     for move in self:
    #         move.message_post(
    #             body=_("Asiento archivado automáticamente en lugar de ser eliminado.")
    #         )

    # def unlink(self):
    #     # 1. BYPASS TOTAL
    #     if self.env.su or self._context.get("force_delete"):
    #         return super().unlink()

    #     # 2. SEPARACIÓN INTELIGENTE
    #     # Identificamos los asientos que DEBEN borrarse físicamente para no romper la sincronización
    #     moves_to_bypass = self.filtered(
    #         lambda m: (
    #             not m.name
    #             or m.name == "/"
    #             or m.payment_id  # El asiento es un Pago
    #             or m.statement_line_id  # El asiento es de una Conciliación Bancaria
    #         )
    #     )

    #     # Los asientos restantes son Facturas o Asientos Manuales
    #     moves_to_soft_delete = self - moves_to_bypass

    #     # Si no hay facturas/asientos manuales que proteger en este lote, borramos todo
    #     if not moves_to_soft_delete:
    #         return super().unlink()

    #     # 3. SEGURIDAD DE USUARIO
    #     if not self.env.user.has_group(
    #         "account_move_protect.group_delete_account_move"
    #     ):
    #         raise AccessError(
    #             _(
    #                 "Seguridad Contable: No tienes permisos para eliminar o archivar asientos. "
    #                 "Solicita autorización a un administrador."
    #             )
    #         )

    #     # 4. LÓGICA DE NEGOCIO
    #     if any(m.state == "posted" for m in moves_to_soft_delete):
    #         raise UserError(
    #             _(
    #                 "No puedes eliminar ni archivar asientos publicados. "
    #                 "Primero debes revertirlos a estado borrador."
    #             )
    #         )

    #     # Archivar únicamente los que están activos y deben protegerse
    #     moves_to_archive = moves_to_soft_delete.filtered("active")
    #     if moves_to_archive:
    #         # Avisamos a Odoo del hueco en la secuencia antes de archivar
    #         moves_to_archive._set_next_made_sequence_gap(True)
    #         moves_to_archive._archive_moves()

    #     # 5. ELIMINACIÓN DEFINITIVA
    #     # Borramos físicamente los del bypass + los que ya estaban archivados previamente
    #     moves_to_hard_delete = self - moves_to_archive
    #     if moves_to_hard_delete:
    #         return super(AccountMove, moves_to_hard_delete).unlink()

    #     return True
