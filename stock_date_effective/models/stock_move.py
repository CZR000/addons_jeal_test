from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if vals.get('date') and vals.get('state', '') == 'done' and rec.picking_id and rec.picking_id.date_done:
                rec.date = rec.picking_id.date_done
        return res

    def _prepare_account_move_vals(self, credit_account_id, debit_account_id, journal_id, qty, description, svl_id, cost):
        res = super(StockMove, self)._prepare_account_move_vals(credit_account_id, debit_account_id, journal_id, qty, description, svl_id, cost)
        svl = self.env['stock.valuation.layer'].browse(svl_id)
        if self.env.context.get('force_period_date'):
            date = self.env.context.get('force_period_date')
        elif self.picking_id and self.picking_id.date_done:
            date = self.picking_id.date_done
        elif svl.account_move_line_id:
            date = svl.account_move_line_id.date
        else:
            date = fields.Date.context_today(self)
        res['date'] = date
        return res

    def _get_currency_conversion_date_for_purchase(self):
        if self.picking_id and self.picking_id.date_done:
            return self.picking_id.date_done
        return fields.Date.context_today(self)

    def _get_price_unit(self):
        if (self.purchase_line_id and
                self.picking_id and
                self.picking_id.date_done):
            conversion_date = self._get_currency_conversion_date_for_purchase()

            return super(StockMove, self.with_context(
                currency_date=conversion_date,
                date=conversion_date
            ))._get_price_unit()

        return super(StockMove, self)._get_price_unit()
