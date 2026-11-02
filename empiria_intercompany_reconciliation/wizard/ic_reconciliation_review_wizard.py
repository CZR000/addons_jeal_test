from odoo import api, fields, models, _
from odoo.exceptions import UserError


class IcReconciliationReviewWizard(models.TransientModel):
    _name = 'ic.reconciliation.review.wizard'
    _description = 'Marcar como revisado (conciliación intercompany)'

    line_ids = fields.Many2many('ic.reconciliation.line', string='Líneas')
    line_count = fields.Integer(compute='_compute_summary')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.ref('base.PEN', raise_if_not_found=False)
                                  or self.env.company.currency_id)
    amount_pen = fields.Monetary(compute='_compute_summary', string='Importe S/')
    comment = fields.Text(string='Comentario', required=True,
                          help='Por qué la diferencia está bien o cuándo se va a regularizar.')

    @api.depends('line_ids')
    def _compute_summary(self):
        for wizard in self:
            wizard.line_count = len(wizard.line_ids)
            wizard.amount_pen = sum(wizard.line_ids.mapped('amount_pen'))

    def action_confirm(self):
        self.ensure_one()
        if not (self.comment or '').strip():
            raise UserError(_('El comentario es obligatorio.'))
        Review = self.env['ic.reconciliation.review']
        for line in self.line_ids.filtered(lambda line: line.status == 'pending'):
            review = Review.create({
                'key': line.review_key,
                'comment': self.comment.strip(),
                'move_line_ids': [(6, 0, line.move_line_ids.ids)],
            })
            line.review_id = review
        self.line_ids.run_id._refresh_counters()
        return {'type': 'ir.actions.act_window_close'}
