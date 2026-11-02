from odoo import models, fields, api


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    accounting_date = fields.Datetime(
        string='Accounting Date',
        compute='_compute_accounting_date',
        inverse='_inverse_accounting_date',
        store=True,
        help='Accounting date obtained from the stock valuation layers associated with the move. '
        'Allows editing the accounting date if the user has the necessary permissions. '
        'Changes made are automatically propagated to all linked valuation layers.',
    )

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)

        if self.env.user.has_group('stock_date_effective.group_edit_accounting_date'):
            for node in arch.xpath("//field[@name='accounting_date']"):
                if view_type == 'form':
                    node.set('readonly', '0')

        return arch, view

    def _action_done(self):
        ml_dates = {}
        for ml in self:
            if ml.picking_id and ml.picking_id.date_done:
                ml_dates[ml.id] = ml.picking_id.date_done
        result = super(StockMoveLine, self)._action_done()
        for ml in self.exists():
            ml_date = ml_dates.get(ml.id) if ml.id in ml_dates else fields.Datetime.now()
            ml.write({'date': ml_date})
        return result

    @api.depends(
        'move_id.stock_valuation_layer_ids.product_id',
        'move_id.stock_valuation_layer_ids.lot_id',
        'move_id.stock_valuation_layer_ids.accounting_date',
        'product_id',
        'lot_id',
    )
    def _compute_accounting_date(self):
        for move_line in self:
            move_line.accounting_date = False
            
            if not (move_line.move_id and move_line.product_id):
                continue
            
            product = move_line.product_id
            lot_id = move_line.lot_id
            check_lot = lot_id and product.lot_valuated
            
            accounting_dates = (
                l.accounting_date for l in move_line.move_id.stock_valuation_layer_ids
                if l.product_id == product 
                and (not check_lot or l.lot_id == lot_id)
                and l.accounting_date
            )
            
            try:
                move_line.accounting_date = max(accounting_dates)
            except ValueError:
                pass

    def _inverse_accounting_date(self):
        LayerModel = self.env['stock.valuation.layer']
        updates = {}
        
        for move_line in self:
            if not (move_line.move_id and move_line.product_id):
                continue
            
            product = move_line.product_id
            lot_id = move_line.lot_id
            check_lot = lot_id and product.lot_valuated
            
            layer_ids = [
                l.id for l in move_line.move_id.stock_valuation_layer_ids
                if l.product_id == product and (not check_lot or l.lot_id == lot_id)
            ]
            
            if layer_ids:
                date_key = move_line.accounting_date or False
                updates.setdefault(date_key, []).extend(layer_ids)
        
        for accounting_date, layer_ids in updates.items():
            LayerModel.browse(layer_ids).write({
                'accounting_date': accounting_date
            })
