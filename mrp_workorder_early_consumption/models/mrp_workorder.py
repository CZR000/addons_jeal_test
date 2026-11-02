# -*- coding: utf-8 -*-
import logging

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero, float_round

_logger = logging.getLogger(__name__)


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    # -------------------------------------------------------------------------
    # Cantidades
    # -------------------------------------------------------------------------
    def _woec_get_produced_qty(self):
        """Cantidad que produce esta orden de trabajo al terminarse, en la
        unidad de medida de la orden de fabricación. Mismo criterio que
        `button_finish` nativo: lo que se está produciendo en la OF o, si no
        se indicó, lo que falta producir."""
        self.ensure_one()
        production = self.production_id
        rounding = production.product_uom_id.rounding
        if not float_is_zero(production.qty_producing, precision_rounding=rounding):
            return production.qty_producing
        return self.qty_remaining

    def _woec_get_component_qty(self, move):
        """Cantidad a consumir de un componente de la lista de materiales,
        proporcional a lo producido (igual que `button_finish` nativo)."""
        production = move.raw_material_production_id
        rounding = production.product_uom_id.rounding
        if float_is_zero(production.qty_producing, precision_rounding=rounding):
            qty_available = production.product_qty
        else:
            qty_available = production.qty_producing
        return float_round(
            qty_available * move.unit_factor,
            precision_rounding=move.product_uom.rounding,
        )

    # -------------------------------------------------------------------------
    # Consumibles del centro de trabajo
    # -------------------------------------------------------------------------
    def _woec_create_consumable_moves(self):
        """Crea los movimientos de los consumibles del centro de trabajo como
        componentes de la OF ligados a esta orden de trabajo. No duplica un
        consumible que ya tenga movimiento (no cancelado) en esta orden."""
        self.ensure_one()
        production = self.production_id
        lines = self.workcenter_id.wo_consumable_line_ids
        if not lines:
            return self.env['stock.move']

        existing_products = production.move_raw_ids.filtered(
            lambda m: m.workorder_id == self
            and m.wo_auto_consumable
            and m.state != 'cancel'
        ).product_id

        vals_list = []
        for line in lines:
            if line.product_id in existing_products:
                continue
            qty = line._get_qty_to_consume(self)
            if float_is_zero(qty, precision_rounding=line.product_uom_id.rounding):
                continue
            vals = production._get_move_raw_values(
                line.product_id,
                qty,
                line.product_uom_id,
                operation_id=self.operation_id.id,
            )
            vals.update({
                'workorder_id': self.id,
                'wo_auto_consumable': True,
            })
            vals_list.append(vals)

        if not vals_list:
            return self.env['stock.move']
        moves = self.env['stock.move'].create(vals_list)
        _logger.info(
            '[WOEC] Consumibles creados para OT %s (OF %s): %s',
            self.id, production.name, moves.ids,
        )
        return moves

    # -------------------------------------------------------------------------
    # Consumo
    # -------------------------------------------------------------------------
    def _woec_get_wo_component_moves(self):
        """Movimientos pendientes de esta orden de trabajo. Antes asigna a
        esta orden los movimientos de la OF de la misma operación que no
        tengan orden de trabajo."""
        self.ensure_one()
        if self.production_id and self.operation_id:
            unassigned = self.production_id.move_raw_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
                and m.operation_id == self.operation_id
                and not m.workorder_id
            )
            if unassigned:
                _logger.info(
                    '[WOEC] Asignando movimientos %s de la OF %s a la OT %s',
                    unassigned.ids, self.production_id.name, self.id,
                )
                unassigned.write({'workorder_id': self.id})
        return self.move_raw_ids.filtered(lambda m: m.state not in ('done', 'cancel'))

    def _woec_prepare_move_quantity(self, move):
        """Deja el movimiento con cantidad y marcado como consumido (`picked`),
        sin lo cual Odoo 18 no lo valida. Si el operario ya lo marcó, se
        respeta la cantidad que registró."""
        if move.state in ('done', 'cancel') or move.picked:
            return

        if move.product_id.tracking != 'none':
            has_lots = move.move_line_ids and all(
                ml.lot_id or ml.lot_name for ml in move.move_line_ids
            )
            if not has_lots or float_is_zero(move.quantity, precision_rounding=move.product_uom.rounding):
                raise UserError(_(
                    "No se puede terminar la orden de trabajo '%(wo)s' de la "
                    "fabricación '%(mo)s': el producto '%(product)s' requiere "
                    "lote o serie. Regístralos antes de terminar la orden de trabajo.",
                    wo=self.display_name,
                    mo=self.production_id.name,
                    product=move.product_id.display_name,
                ))
            move.picked = True
            return

        if move.wo_auto_consumable:
            qty = move.product_uom_qty
        else:
            qty = self._woec_get_component_qty(move)
        if float_is_zero(qty, precision_rounding=move.product_uom.rounding):
            return
        move._set_quantity_done(qty)
        move.picked = True

    def _woec_confirm_assign_and_done(self, moves):
        """Confirma, reserva y valida los movimientos de la orden de trabajo.

        Si la validación falla (falta stock, cuenta contable, ubicación...),
        se muestra el error con la orden de trabajo y la OF. No se pasa en
        silencio al flujo nativo: un fallo oculto dejaría la analítica o la
        valoración descuadradas sin que nadie lo note.
        """
        moves = moves.filtered(lambda m: m.state not in ('done', 'cancel'))
        if not moves:
            return

        moves_to_confirm = moves.filtered(lambda m: m.state == 'draft')
        if moves_to_confirm:
            # Sin fusionar: un consumible puede ser el mismo producto que un
            # componente de la lista de materiales.
            moves_to_confirm._action_confirm(merge=False)
        moves_to_assign = moves.filtered(
            lambda m: m.state in ('confirmed', 'waiting', 'partially_available')
        )
        if moves_to_assign:
            moves_to_assign._action_assign()

        for move in moves:
            self._woec_prepare_move_quantity(move)

        moves_to_done = moves.filtered(lambda m: m.picked and m.state not in ('done', 'cancel'))
        if not moves_to_done:
            return
        try:
            moves_to_done.with_context(woec_force_valuation=True)._action_done()
        except UserError:
            raise
        except Exception as e:
            _logger.exception(
                '[WOEC] Falló el consumo de la OT %s (OF %s)',
                self.id, self.production_id.name,
            )
            raise UserError(_(
                "No se pudieron consumir los componentes de la orden de trabajo "
                "'%(wo)s' de la fabricación '%(mo)s'.\n\n"
                "Detalle técnico: %(error)s\n\n"
                "Revisa el stock disponible, las cuentas contables del producto "
                "y las ubicaciones, y vuelve a intentarlo.",
                wo=self.display_name,
                mo=self.production_id.name,
                error=str(e),
            )) from e
        _logger.info(
            '[WOEC] OT %s consumió: %s',
            self.id, ', '.join(f'{m.id}:{m.state}' for m in moves_to_done),
        )

    def _woec_early_consume_on_finish(self):
        for wo in self.filtered(lambda w: w.state not in ('done', 'cancel')):
            production = wo.production_id
            if not production or production.state in ('done', 'cancel'):
                continue
            wo._woec_create_consumable_moves()
            moves = wo._woec_get_wo_component_moves()
            wo._woec_confirm_assign_and_done(moves)

    def button_finish(self):
        self._woec_early_consume_on_finish()
        return super().button_finish()

    def button_done(self):
        self._woec_early_consume_on_finish()
        return super().button_done()
