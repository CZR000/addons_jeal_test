from odoo import fields, models


class MRPProduction(models.Model):
    _inherit = 'mrp.production'

    partner_id = fields.Many2one(
        string='Cliente',
        comodel_name='res.partner',
    )

    def action_confirm(self):
        """Override v18: en lugar de duplicar todo el cuerpo de
        `super().action_confirm()` (frágil ante cambios de upstream), llamamos
        a super y luego propagamos `partner_id` (cliente de la OF) hacia
        `picking.owner_id` y todas las `move.line.owner_id` de los pickings
        recién confirmados.

        Diferencia respecto al v16: el v16 copy-pasteaba la implementación
        nativa antes de su bloque custom. En v18 el método nativo cambió
        sutilmente (sigue idéntico en estructura, pero podría evolucionar
        en parches menores). Usar super() es más robusto y mantiene la
        misma intención funcional 1:1.
        """
        res = super().action_confirm()

        # ----- BLOQUE CUSTOM (preservado del v16) ----- #
        # Asignar owner_id a los pickings recién confirmados y a sus líneas
        # de movimiento desde el partner_id (Cliente) de la MO.
        for production in self:
            if not production.partner_id:
                continue
            pickings_to_update = production.picking_ids.filtered(
                lambda p: p.state not in ['cancel', 'done']
            )
            if not pickings_to_update:
                continue
            pickings_to_update.write({'owner_id': production.partner_id.id})
            move_lines_to_update = pickings_to_update.mapped('move_line_ids')
            if move_lines_to_update:
                move_lines_to_update.write({'owner_id': production.partner_id.id})
        # ----- FIN BLOQUE CUSTOM ----- #

        return res
