from odoo import api, fields, models


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    valuation_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Valuation Account",
        compute="_compute_valuation_account_id",
        store=True,
        readonly=True,
        index="btree_not_null",
        help="Stock valuation account of the product category, read for the "
             "company of the layer. Empty when the category uses manual "
             "(periodic) valuation. Reflects the current category "
             "configuration, not the account used in the journal entry.",
    )

    @api.depends(
        "categ_id",
        "categ_id.property_valuation",
        "categ_id.property_stock_valuation_account_id",
        "company_id",
    )
    def _compute_valuation_account_id(self):
        for layer in self:
            categ = layer.categ_id.with_company(layer.company_id)
            if categ and categ.property_valuation == "real_time":
                layer.valuation_account_id = categ.property_stock_valuation_account_id
            else:
                layer.valuation_account_id = False

    def _recompute_valuation_account(self):
        """Force recompute (e.g. after changing company-level defaults,
        which do not trigger the stored compute)."""
        field = self._fields["valuation_account_id"]
        self.env.add_to_compute(field, self)
        self.flush_recordset(["valuation_account_id"])
        return True
