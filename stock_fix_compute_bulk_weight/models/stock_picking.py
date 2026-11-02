from collections import defaultdict
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.depends(
        'move_line_ids',
        'move_line_ids.result_package_id',
        'move_line_ids.product_uom_id',
        'move_line_ids.quantity',
    )
    def _compute_bulk_weight(self):
        # Override v18: usa la nueva firma de `_read_group` (devuelve
        # recordsets en lugar de IDs) y el campo `quantity` que en v17
        # reemplazó a `qty_done` en stock.move.line.
        # Mantiene la protección defensiva del módulo original: si el
        # producto agrupado no existe (referencia colgante o producto
        # eliminado), se omite la fila y se registra un warning en lugar
        # de propagar un KeyError.
        picking_weights = defaultdict(float)
        res_groups = self.env['stock.move.line']._read_group(
            [
                ('picking_id', 'in', self.ids),
                ('product_id', '!=', False),
                ('result_package_id', '=', False),
            ],
            ['picking_id', 'product_id', 'product_uom_id', 'quantity'],
            ['__count'],
        )
        for picking, product, product_uom, quantity, count in res_groups:
            if not product.exists():
                _logger.warning(
                    'Product %s not found in bulk weight calculation '
                    'for picking %s. Skipping.',
                    product.id, picking.id,
                )
                continue
            picking_weights[picking.id] += (
                count
                * product_uom._compute_quantity(quantity, product.uom_id)
                * product.weight
            )
        for picking in self:
            picking.weight_bulk = picking_weights[picking.id]
