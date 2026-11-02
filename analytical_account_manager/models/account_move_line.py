from odoo import _, api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends("move_id.stock_move_id.picking_id.analytic_account_id")
    def _compute_analytic_distribution(self):
        """
        Agrega la distribución analítica heredada desde el inventario
        """
        super()._compute_analytic_distribution()

        for line in self:
            stock_move = line.move_id.stock_move_id
            if not stock_move or line.move_id.is_invoice(include_receipts=True):
                continue

            picking_analytic = stock_move.picking_id.analytic_account_id
            if picking_analytic:
                # Recuperamos el diccionario actual para no sobreescribir
                current_distribution = line.analytic_distribution or {}
                # Inyectamos nuestra cuenta analítica
                current_distribution[str(picking_analytic.id)] = 100
                line.analytic_distribution = current_distribution
