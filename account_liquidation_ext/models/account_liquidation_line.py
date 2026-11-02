from odoo import api, fields, models


PAYMENT_STATE_SELECTION = [
    ('not_paid', 'No pagado'),
    ('in_payment', 'En pago'),
    ('paid', 'Pagado'),
    ('partial', 'Parcialmente pagado'),
    ('reversed', 'Revertido'),
    ('invoicing_legacy', 'Legacy'),
]


class AccountLiquidationLine(models.Model):
    _inherit = 'account.liquidation.line'

    payment_state = fields.Selection(

        string='Estado de pago',
        related='move_id.payment_state',
        store=True,
    )
    amount_paid = fields.Monetary(
        string='Importe pagado',
        compute='_compute_amount_paid',
        store=True,
        currency_field='company_currency_id',
    )

    usd_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda USD',
        compute='_compute_usd_currency_id',
        store=True,
    )
    total_usd = fields.Monetary(
        string='Total USD',
        compute='_compute_usd_amounts',
        store=True,
        currency_field='usd_currency_id',
    )

    @api.depends('company_id')
    def _compute_usd_currency_id(self):
        usd = self.env.ref('base.USD')
        for rec in self:
            rec.usd_currency_id = usd

    @api.depends('total', 'move_currency_id', 'company_currency_id')
    def _compute_usd_amounts(self):
        usd = self.env.ref('base.USD')
        for rec in self:
            if rec.move_currency_id == usd and rec.move_currency_id != rec.company_currency_id:
                rec.total_usd = rec.total
            else:
                rec.total_usd = 0.0

    @api.depends(
        'move_id',
        'move_id.amount_total',
        'move_id.amount_residual',
        'move_id.currency_id',
        'company_currency_id',
        'company_id',
    )
    def _compute_amount_paid(self):
        for rec in self:
            if not rec.move_id:
                rec.amount_paid = 0.0
                continue
            move = rec.move_id
            paid = move.amount_total - move.amount_residual
            date = move.invoice_date or move.date or fields.Date.context_today(rec)
            rec.amount_paid = move.currency_id._convert(
                paid,
                rec.company_currency_id,
                rec.company_id,
                date,
            )
