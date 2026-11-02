from odoo import _, api, fields, models


class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    def _prepare_picking_default_values_based_on(self, picking):
        """
        Inyectamos las cuentas analíticas directamente en el diccionario de creación.
        """
        vals = super()._prepare_picking_default_values_based_on(picking)

        if picking.analytic_plan_id:
            vals["analytic_plan_id"] = picking.analytic_plan_id.id
        if picking.analytic_account_id:
            vals["analytic_account_id"] = picking.analytic_account_id.id

        return vals

    def _create_return(self):
        """
        Propagar la información analítica de un albarán original hacia su devolución
        """
        # Llamamos al padre para que cree el picking
        new_picking = super()._create_return()

        # Propagar datos analíticos a las líneas de movimiento
        for move in new_picking.move_ids:
            original_move = move.origin_returned_move_id
            if not original_move:
                continue

            # Buscamos la primera move_line original que tenga datos analíticos
            source_line = original_move.move_line_ids.filtered(
                lambda ml: ml.analytic_plan_id or ml.analytic_id
            )[:1]

            if source_line and move.move_line_ids:
                # Escribimos de un solo golpe en todas las líneas del movimiento
                move.move_line_ids.write(
                    {
                        "analytic_plan_id": source_line.analytic_plan_id.id,
                        "analytic_id": source_line.analytic_id.id,
                    }
                )

        return new_picking
