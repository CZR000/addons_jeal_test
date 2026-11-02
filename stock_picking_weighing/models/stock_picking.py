from odoo import _, api, fields, models
from odoo.exceptions import ValidationError



class StockPicking(models.Model):
    _inherit = 'stock.picking'

    initial_weight = fields.Float(
        string='Peso inicial',
        digits='Product Unit of Measure',
        copy=False
    )
    initial_weight_at = fields.Datetime(
        string='Fecha y hora inicial',
        copy=False
    )
    final_weight = fields.Float(
        string='Peso final',
        digits='Product Unit of Measure',
        copy=False
    )
    final_weight_at = fields.Datetime(
        string='Fecha y hora final',
        copy=False
    )
    
    @api.onchange('initial_weight', 'final_weight', 'initial_weight_at', 'final_weight_at')
    def _onchange_propagate_weighing_to_moves(self):
        for picking in self:
            for move in picking.move_ids_without_package:
                move.initial_weight = picking.initial_weight
                move.final_weight = picking.final_weight

    def write(self, vals):
        res = super().write(vals)
        keys = {'initial_weight', 'final_weight'}
        if keys.intersection(vals.keys()):
            for picking in self:
                picking.move_ids_without_package.write({
                    'initial_weight': picking.initial_weight,
                    'final_weight': picking.final_weight,
                })
        return res

    @api.constrains('initial_weight', 'final_weight')
    def _check_weighing(self):
        for picking in self:
            if (picking.initial_weight or 0.0) < 0.0 or (picking.final_weight or 0.0) < 0.0:
                raise ValidationError('Los pesos no pueden ser negativos.')
            if picking.initial_weight and picking.final_weight and picking.final_weight < picking.initial_weight:
                raise ValidationError('El peso final no puede ser menor que el peso inicial.')

    @api.constrains('initial_weight', 'initial_weight_at', 'final_weight', 'final_weight_at')
    def _check_weight_dates_required(self):
        for picking in self:
            if picking.initial_weight and not picking.initial_weight_at:
                raise ValidationError('Ingrese la fecha y hora inicial del pesaje.')
            if picking.final_weight and not picking.final_weight_at:
                raise ValidationError('Ingrese la fecha y hora final del pesaje.')

    @api.constrains('initial_weight_at', 'final_weight_at')
    def _check_dates(self):
        for picking in self:
            if picking.initial_weight_at and picking.final_weight_at:
                if picking.final_weight_at < picking.initial_weight_at:
                    raise ValidationError('La fecha y hora final de peso no puede ser menor que la fecha y hora inicial de peso.')
