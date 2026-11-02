from odoo import models
from odoo.tools.sql import create_index


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    # ``kardex_cost_correction`` is defined in ``stock_product_cost_change_log``
    # (a shared base both this report and the SUNAT 13.1 report depend on) so
    # the column is always available to filter the correction layers out of any
    # WAC recomputation.

    def init(self):
        create_index(
            self.env.cr,
            'svl_kardex_company_date_product_idx',
            self._table,
            ['company_id', 'COALESCE(accounting_date, create_date)', 'product_id'],
        )
