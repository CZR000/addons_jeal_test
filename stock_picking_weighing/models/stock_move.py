from odoo import _, api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    initial_weight = fields.Float(
        string='Peso inicial',
        digits='Product Unit of Measure',
        copy=False
    )
    final_weight = fields.Float(
        string='Peso final',
        digits='Product Unit of Measure',
        copy=False
    )
    weight_diff = fields.Float(
        string='Diferencia pesos',
        digits='Product Unit of Measure',
        compute='_compute_weight_diff',
        store=True
    )

    @api.onchange('final_weight', 'initial_weight')
    def _onchange_qty_done(self):
        # En Odoo 18 el campo `quantity_done` fue reemplazado por `quantity`
        # (computed/stored con inverse `_set_quantity`).
        weight_diff = self.initial_weight - self.final_weight
        self.quantity = weight_diff

    @api.depends('initial_weight', 'final_weight')
    def _compute_weight_diff(self):
        for rec in self:
            rec.weight_diff = (rec.initial_weight or 0.0) - (rec.final_weight or 0.0)
