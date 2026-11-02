from odoo import api, fields, models

from ..engine import BLOCK_LABELS, CATEGORIES, PENDING_CATEGORIES

BLOCK_SELECTION = list(BLOCK_LABELS.items())


class IcReconciliationPair(models.Model):
    _name = 'ic.reconciliation.pair'
    _description = 'Par de empresas en la conciliación intercompany'
    _order = 'run_id desc, abs_difference desc, id'

    run_id = fields.Many2one('ic.reconciliation.run', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='run_id.currency_id')
    date_from = fields.Date(related='run_id.date_from', store=True, string='Desde')
    date_to = fields.Date(related='run_id.date_to', store=True, string='Hasta')
    is_last = fields.Boolean(related='run_id.is_last', store=True, string='Última ejecución')
    company_a_id = fields.Many2one('res.company', string='Empresa A', required=True)
    company_b_id = fields.Many2one('res.company', string='Empresa B', required=True)
    block = fields.Selection(BLOCK_SELECTION, string='Bloque', required=True,
                             help='Quién cobra: las cuentas por cobrar de una empresa contra las por pagar de la otra.')
    block_name = fields.Char(compute='_compute_block_name', string='Quién cobra')
    total_difference = fields.Monetary(string='Total del par',
                                       help='Diferencia de los dos bloques del par (A cobra y B cobra).')
    balance_a = fields.Monetary(string='Saldo A con B', help='Saldo en soles de la empresa A con la empresa B.')
    balance_b = fields.Monetary(string='Saldo B con A', help='Saldo en soles de la empresa B con la empresa A.')
    difference = fields.Monetary(string='Diferencia', help='Saldo A con B + saldo B con A: debería ser 0.')
    opening_a = fields.Monetary(string='Saldo inicial A con B', help='Saldo de A con B el día anterior a la fecha desde.')
    opening_b = fields.Monetary(string='Saldo inicial B con A', help='Saldo de B con A el día anterior a la fecha desde.')
    opening_difference = fields.Monetary(string='Diferencia al inicio',
                                         help='Diferencia entre los saldos el día anterior a la fecha desde.')
    abs_difference = fields.Monetary(compute='_compute_abs_difference', store=True)
    control = fields.Monetary(string='Control', help='Diferencia − suma de las categorías: debe ser 0.')
    matched_count = fields.Integer(string='Conciliados')
    pending_count = fields.Integer(string='Pendientes')
    reviewed_count = fields.Integer(string='Revisados')
    state = fields.Selection(
        selection=[('balanced', 'Cuadra'), ('pending', 'Por conciliar'), ('reviewed', 'Revisado')],
        compute='_compute_state', store=True, string='Estado')
    line_ids = fields.One2many('ic.reconciliation.line', 'pair_id', string='Detalle')

    # Una columna por categoría (desglose de la diferencia).
    for _key, _label, _hint in CATEGORIES:
        locals()[f'amount_{_key}'] = fields.Monetary(string=_label, help=_hint or None)
    del _key, _label, _hint

    @api.depends('difference')
    def _compute_abs_difference(self):
        for pair in self:
            pair.abs_difference = abs(pair.difference)

    @api.depends('difference', 'pending_count', 'reviewed_count')
    def _compute_state(self):
        for pair in self:
            if abs(pair.difference) < 0.005:
                pair.state = 'balanced'
            elif not pair.pending_count:
                pair.state = 'reviewed'
            else:
                pair.state = 'pending'

    @api.depends('company_a_id', 'company_b_id', 'block')
    def _compute_block_name(self):
        for pair in self:
            creditor, debtor = ((pair.company_a_id, pair.company_b_id) if pair.block == 'a_receivable'
                                else (pair.company_b_id, pair.company_a_id))
            pair.block_name = f"{creditor.name} por cobrar / {debtor.name} por pagar" if creditor else ''

    @api.depends('company_a_id', 'company_b_id', 'block')
    def _compute_display_name(self):
        for pair in self:
            pair.display_name = f"{pair.company_a_id.name} ↔ {pair.company_b_id.name} · {dict(BLOCK_SELECTION).get(pair.block)}"

    def action_open_lines(self, category=None):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('empiria_intercompany_reconciliation.action_ic_reconciliation_line')
        domain = [('pair_id', '=', self.id)]
        context = {'search_default_group_category': 1}
        category = category or self.env.context.get('ic_category')
        if category:
            domain.append(('category', '=', category))
        else:
            context['search_default_filter_pending'] = 1
        action.update({'domain': domain, 'context': context, 'name': self.display_name})
        return action

    def action_open_category(self):
        return self.action_open_lines(self.env.context.get('ic_category'))

    def _category_amounts(self):
        """[(categoría, etiqueta, importe)] con importe distinto de cero."""
        self.ensure_one()
        return [(key, label, self[f'amount_{key}']) for key, label, _hint in CATEGORIES
                if abs(self[f'amount_{key}']) >= 0.005]

    @api.model
    def _pending_categories(self):
        return PENDING_CATEGORIES
