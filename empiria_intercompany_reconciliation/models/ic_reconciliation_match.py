from odoo import api, fields, models

MATCH_REASONS = [
    ('grouped', 'Pago agrupado'),
    ('triangular', 'Compensación entre 3 empresas'),
    ('exchange_rate', 'Tipo de cambio'),
    ('commission', 'Comisión o gasto bancario'),
    ('other', 'Otro (con explicación)'),
]


class IcReconciliationManualMatch(models.Model):
    """Apuntes que el usuario unió a mano. Se conserva entre ejecuciones: la
    siguiente ejecución los clasifica como "Conciliado manual"."""
    _name = 'ic.reconciliation.manual.match'
    _description = 'Emparejamiento manual de la conciliación intercompany'
    _order = 'date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    line_ids_a = fields.Many2many('account.move.line', relation='ic_manual_match_aml_a_rel',
                                  column1='match_id', column2='aml_id', string='Apuntes de un lado')
    line_ids_b = fields.Many2many('account.move.line', relation='ic_manual_match_aml_b_rel',
                                  column1='match_id', column2='aml_id', string='Apuntes de la otra empresa')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.ref('base.PEN', raise_if_not_found=False)
                                  or self.env.company.currency_id)
    difference_pen = fields.Monetary(string='Diferencia aceptada')
    reason = fields.Selection(MATCH_REASONS, string='Motivo', required=True)
    reason_note = fields.Text(string='Explicación')
    user_id = fields.Many2one('res.users', string='Emparejado por', default=lambda self: self.env.user, readonly=True)
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now, readonly=True)
    active = fields.Boolean(default=True, help='Deshacer el emparejamiento lo archiva.')

    @api.depends('line_ids_a', 'line_ids_b')
    def _compute_name(self):
        for match in self:
            moves = (match.line_ids_a | match.line_ids_b).move_id
            match.name = ' + '.join(moves.mapped('name')[:4]) or '/'

    def _reason_text(self):
        self.ensure_one()
        label = dict(MATCH_REASONS).get(self.reason, '')
        return f"{label}: {self.reason_note}" if self.reason_note else label


class IcReconciliationReview(models.Model):
    """Revisión de una diferencia justificada. Se reconoce en otras ejecuciones
    por su huella (empresa + asiento + importe)."""
    _name = 'ic.reconciliation.review'
    _description = 'Revisión de la conciliación intercompany'
    _order = 'date desc, id desc'
    _rec_name = 'key'

    move_line_ids = fields.Many2many('account.move.line', relation='ic_review_aml_rel',
                                     column1='review_id', column2='aml_id', string='Apuntes revisados')
    key = fields.Char(string='Huella', required=True, index=True)
    comment = fields.Text(string='Comentario', required=True)
    user_id = fields.Many2one('res.users', string='Revisado por', default=lambda self: self.env.user, readonly=True)
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now, readonly=True)
    active = fields.Boolean(default=True, help='Deshacer la revisión la archiva.')
