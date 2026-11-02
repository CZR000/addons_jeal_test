from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    def _prepare_default_reversal(self, move):
        """
        Prepara los valores por defecto para la reversión de un asiento contable.

        Extiende la lógica original para incluir el comercial externo asociado
        al asiento (si existe).

        :param move: registro de account.move que se está revirtiendo
        :return: diccionario de valores por defecto para la reversión
        """
        values = super()._prepare_default_reversal(move)

        if move.external_commercial_id:
            values["external_commercial_id"] = move.external_commercial_id.id

        return values
