# -*- coding: utf-8 -*-
import logging

from odoo import Command, models

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def _woec_get_done_consumed_moves(self):
        """Componentes y consumibles de la OF ya consumidos (hacia la
        ubicación de producción), sin desechos."""
        self.ensure_one()
        return self.move_raw_ids.filtered(
            lambda m: m.state == 'done'
            and not m.scrapped
            and m.location_dest_id.usage == 'production'
        )

    def _cal_price(self, consumed_moves):
        """Al cerrar la OF, Odoo solo pasa los movimientos que valida en ese
        momento. Los consumidos antes, al terminar cada orden de trabajo,
        quedarían fuera del costo del producto terminado; aquí se suman."""
        for production in self:
            moves = consumed_moves.filtered(
                lambda m: m.raw_material_production_id == production
            ) | production._woec_get_done_consumed_moves()
            super(MrpProduction, production)._cal_price(moves)
        return True

    def _post_inventory(self, cancel_backorder=False):
        """Odoo enlaza al producto terminado solo las líneas consumidas al
        cerrar la OF. Se enlazan también las consumidas antes, para que la
        trazabilidad de lotes muestre todos los componentes."""
        res = super()._post_inventory(cancel_backorder=cancel_backorder)
        for production in self:
            consumed_lines = production._woec_get_done_consumed_moves().move_line_ids
            finished_lines = production.move_finished_ids.filtered(
                lambda m: m.state == 'done'
            ).move_line_ids
            if consumed_lines and finished_lines:
                finished_lines.write({'consume_line_ids': [Command.set(consumed_lines.ids)]})
        return res
