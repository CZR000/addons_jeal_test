from odoo import api, fields, models


class ReportLiquidation(models.Model):
    _inherit = 'report.liquidation'

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
    )
    balance_to_settle = fields.Monetary(
        string='Saldo por liquidar',
        compute='_compute_balance_to_settle',
        store=True,
        currency_field='currency_id',
    )

    @api.depends(
        'transport_ids.total_company',
        'process_ids.total_company',
        'invoiced_ids.total_company',
    )
    def _compute_balance_to_settle(self):
        for rec in self:
            transport = sum(rec.transport_ids.mapped('total_company'))
            process = sum(rec.process_ids.mapped('total_company'))
            invoiced = sum(rec.invoiced_ids.mapped('total_company'))
            rec.balance_to_settle = invoiced - transport - process

    def _get_all_move_ids(self):
        """Return all account.move records from the 3 tabs."""
        self.ensure_one()
        moves = self.env['account.move']
        for line in self.transport_ids | self.process_ids | self.invoiced_ids:
            if line.move_id:
                moves |= line.move_id
        return moves

    def action_done(self):
        for rec in self:
            moves = rec._get_all_move_ids()
            if moves:
                moves.write({'liquidation_name': rec.name})
        return super().action_done()

    def action_to_draft(self):
        for rec in self:
            moves = rec._get_all_move_ids()
            if moves:
                moves.write({'liquidation_name': False})
        return super().action_to_draft()
