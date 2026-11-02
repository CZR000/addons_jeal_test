from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        date_done = self.date_done
        res = super(StockPicking, self)._action_done()
        if date_done:
            self.write({'date_done': date_done})
        return res
