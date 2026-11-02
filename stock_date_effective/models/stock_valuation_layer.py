from datetime import datetime
from odoo import api, fields, models


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    accounting_date = fields.Datetime(
        string='Accounting Date',
        default=datetime.now()
    )

    @api.model_create_multi
    def create(self, vals_list):
        for val in vals_list:
            if val.get('stock_move_id', False):
                move = self.env['stock.move'].browse(val['stock_move_id'])
                val['accounting_date'] = move.date if move else datetime.now()
        return super(StockValuationLayer, self).create(vals_list)

    def _edit_fields_views(self, arch, view):
        if self.env.user.has_group('stock_date_effective.group_edit_accounting_date'):
            for node in arch.xpath("//field[@name='accounting_date']"):
                node.set('readonly', '0')
        return arch, view

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            for node in arch.xpath("//form"):
                node.set('edit', '1')
            for node in arch.xpath("//field"):
                node.set('readonly', '1')
        if view_type == 'list':
            for node in arch.xpath("//list"):
                node.set('editable', 'top')
            for node in arch.xpath("//field"):
                node.set('readonly', '1')
        arch, view = self._edit_fields_views(arch, view)
        return arch, view

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type='form', **options):
        key = super()._get_view_cache_key(view_id, view_type, **options)
        return key + (
            self.env.user.has_group('stock_date_effective.group_edit_accounting_date'),
        )
