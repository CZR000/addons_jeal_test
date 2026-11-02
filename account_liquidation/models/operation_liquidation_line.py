from odoo import _, api, fields, models


class OperationLiquidation(models.Model):
    _name = 'operation.liquidation.line'
    _description = 'Operaciones de liquidación'
    _check_company_auto = True

    _sql_constraints = [
        ('uniq_liq_move', 'UNIQUE(liquidation_id, move_id)', 'Este movimiento ya está en la liquidación.')
    ]

    liquidation_id = fields.Many2one(
        string='Liquidación',
        comodel_name='report.liquidation',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        string='Compañia',
        comodel_name='res.company',
        related='liquidation_id.company_id',
        store=True
    )
    picking_id = fields.Many2one(
        string='Recepción',
        comodel_name='stock.picking',
        check_company=True
    )
    delivery_note = fields.Char(
        string='Guia',
        related='picking_id.l10n_latam_document_number',
        store=True
    )
    move_id = fields.Many2one(
        string='Operación',
        comodel_name='stock.move',
        check_company=True
    )
    product_id = fields.Many2one(
        string='Producto',
        comodel_name='product.product',
        related='move_id.product_id',
        store=True
    )
    initial_weight = fields.Float(
        string='Peso inicial',
        digits='Product Unit of Measure',
        related='move_id.initial_weight',
        store=True
    )
    final_weight = fields.Float(
        string='Peso final',
        digits='Product Unit of Measure',
        related='move_id.final_weight',
        store=True
    )
    qty_done = fields.Float(
        string='Realizado',
        digits='Product Unit of Measure',
        # Odoo 18: stock.move.quantity_done fue eliminado en v18.
        # Ahora la cantidad realmente movida vive en `quantity` (Float,
        # compute/stored con inverse `_set_quantity`).
        related='move_id.quantity',
        store=True
    )
