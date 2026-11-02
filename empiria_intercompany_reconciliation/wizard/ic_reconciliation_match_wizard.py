from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models.ic_reconciliation_match import MATCH_REASONS


class IcReconciliationMatchWizard(models.TransientModel):
    _name = 'ic.reconciliation.match.wizard'
    _description = 'Emparejar a mano (conciliación intercompany)'

    line_ids = fields.Many2many('ic.reconciliation.line', string='Líneas')
    detail_ids = fields.One2many('ic.reconciliation.match.wizard.line', 'wizard_id', compute='_compute_details')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.ref('base.PEN', raise_if_not_found=False)
                                  or self.env.company.currency_id)
    difference_pen = fields.Monetary(compute='_compute_details', string='Diferencia que se acepta (S/)')
    difference_currency = fields.Float(compute='_compute_details', string='Diferencia en moneda')
    difference_currency_name = fields.Char(compute='_compute_details')
    reason = fields.Selection(MATCH_REASONS, string='Motivo', required=True, default='other')
    reason_note = fields.Text(string='Explicación')

    @api.depends('line_ids')
    def _compute_details(self):
        for wizard in self:
            wizard.detail_ids = [(5,)] + [(0, 0, {'line_id': line.id}) for line in wizard.line_ids]
            wizard.difference_pen = sum(wizard.line_ids.mapped('amount_pen'))
            currencies = wizard.line_ids.line_currency_id
            if len(currencies) == 1:
                wizard.difference_currency = sum(wizard.line_ids.mapped('amount_currency'))
                wizard.difference_currency_name = currencies.name
            else:
                wizard.difference_currency = 0.0
                wizard.difference_currency_name = ''

    def action_confirm(self):
        self.ensure_one()
        lines = self.line_ids
        lines._check_match_lines()
        if not self.currency_id.is_zero(self.difference_pen) and not (self.reason_note or '').strip():
            raise UserError(_('Hay una diferencia de %s: la explicación es obligatoria.', self.currency_id.format(self.difference_pen)))
        first_company = lines[0].company_id
        move_lines = lines.move_line_ids | lines.counterpart_line_ids
        side_a = move_lines.filtered(lambda aml: aml.company_id == first_company)
        if not move_lines:
            raise UserError(_('Las líneas elegidas no tienen apuntes que emparejar (p.ej. la diferencia de cambio agregada).'))
        match = self.env['ic.reconciliation.manual.match'].create({
            'line_ids_a': [(6, 0, side_a.ids)],
            'line_ids_b': [(6, 0, (move_lines - side_a).ids)],
            'difference_pen': self.difference_pen,
            'reason': self.reason,
            'reason_note': (self.reason_note or '').strip(),
        })
        for line in lines.filtered(lambda line: line.category != 'manual_match'):
            # Para volver a la categoría anterior si se deshace el emparejamiento.
            line.write({'original_category': line.category, 'original_note': line.note})
        lines.write({
            'category': 'manual_match',
            'is_pending': False,
            'manual_match_id': match.id,
            'note': match._reason_text(),
            'action_hint': _('Emparejado a mano por %s.', self.env.user.name),
        })
        lines.run_id._refresh_counters()
        return {'type': 'ir.actions.act_window_close'}


class IcReconciliationMatchWizardLine(models.TransientModel):
    _name = 'ic.reconciliation.match.wizard.line'
    _description = 'Línea a emparejar a mano'

    wizard_id = fields.Many2one('ic.reconciliation.match.wizard', ondelete='cascade')
    line_id = fields.Many2one('ic.reconciliation.line')
    company_id = fields.Many2one(related='line_id.company_id', string='Empresa')
    move_name = fields.Char(related='line_id.move_name', string='Asiento')
    date = fields.Date(related='line_id.date', string='Fecha')
    account_code = fields.Char(related='line_id.account_code', string='Cuenta')
    label = fields.Char(related='line_id.label', string='Glosa')
    line_currency_id = fields.Many2one(related='line_id.line_currency_id', string='Moneda')
    amount_currency = fields.Monetary(related='line_id.amount_currency', currency_field='line_currency_id', string='Importe moneda')
    currency_id = fields.Many2one(related='line_id.currency_id')
    amount_pen = fields.Monetary(related='line_id.amount_pen', string='S/')
