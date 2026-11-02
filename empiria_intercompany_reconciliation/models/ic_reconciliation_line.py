from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..engine import CATEGORIES, CATEGORY_HINTS

CATEGORY_SELECTION = [(key, label) for key, label, _hint in CATEGORIES]
RULES = [
    (1, 'Universo'), (2, 'Diferencia de cambio automática'), (3, 'Comprobante por número'),
    (4, 'Comprobante emparejado'), (5, 'Serie distinta'), (6, 'Número distinto'),
    (7, 'Búsqueda en el receptor'), (8, 'Comprobante sin par'), (9, 'Anulado en la misma empresa'),
    (10, 'Pago ↔ cobro'), (11, 'Pago en otra moneda'), (12, 'Pagos agrupados'),
    (13, 'Compensación de 3 empresas / registrado del mismo lado'), (14, 'Emparejamiento manual'), (15, 'Sin par'),
    (16, 'Pago más retención'), (17, 'Un pago contra varios'), (18, 'Anticipo o préstamo en varias partes'),
]
RULE_PRIOR = 'Anterior al periodo'


class IcReconciliationLine(models.Model):
    _name = 'ic.reconciliation.line'
    _description = 'Detalle de la conciliación intercompany'
    _order = 'run_id desc, pair_id, category, abs_effect desc, id'

    run_id = fields.Many2one('ic.reconciliation.run', required=True, ondelete='cascade', index=True)
    pair_id = fields.Many2one('ic.reconciliation.pair', string='Par', required=True, ondelete='cascade', index=True)
    block = fields.Selection(related='pair_id.block', store=True)
    run_date_from = fields.Date(related='run_id.date_from', store=True, string='Periodo desde')
    run_date_to = fields.Date(related='run_id.date_to', store=True, string='Periodo hasta')
    is_last = fields.Boolean(related='run_id.is_last', store=True, string='Última ejecución')
    currency_id = fields.Many2one(related='run_id.currency_id')
    category = fields.Selection(CATEGORY_SELECTION, string='Categoría', required=True, index=True)
    rule = fields.Integer(string='Regla')
    rule_name = fields.Char(compute='_compute_rule_name', string='Regla aplicada')
    company_id = fields.Many2one('res.company', string='Registrado en', required=True, index=True)
    counterpart_company_id = fields.Many2one('res.company', string='Contraparte')
    move_id = fields.Many2one('account.move', string='Asiento', index='btree_not_null')
    move_line_ids = fields.Many2many(
        'account.move.line', relation='ic_reconciliation_line_aml_rel', column1='line_id', column2='aml_id',
        string='Apuntes')
    counterpart_move_id = fields.Many2one('account.move', string='Documento en la contraparte')
    counterpart_line_ids = fields.Many2many(
        'account.move.line', relation='ic_reconciliation_line_counterpart_aml_rel', column1='line_id',
        column2='aml_id', string='Apuntes de la contraparte')
    move_name = fields.Char(string='Asiento (número)')
    counterpart_move_name = fields.Char(string='Asiento en la contraparte')
    doc_type = fields.Selection(
        selection=[('invoice', 'Factura'), ('refund', 'Nota de crédito'), ('debit', 'Nota de débito')],
        string='Tipo')
    doc_number = fields.Char(string='Comprobante', help='Serie-número normalizados.')
    date = fields.Date(string='Fecha')
    counterpart_date = fields.Date(string='Fecha en la contraparte')
    line_currency_id = fields.Many2one('res.currency', string='Moneda')
    amount_currency = fields.Monetary(string='Importe moneda', currency_field='line_currency_id')
    amount_pen = fields.Monetary(string='Importe S/')
    counterpart_currency_id = fields.Many2one('res.currency', string='Moneda contraparte')
    counterpart_amount_currency = fields.Monetary(string='Importe contraparte', currency_field='counterpart_currency_id')
    counterpart_amount_pen = fields.Monetary(string='Importe contraparte S/')
    effect_pen = fields.Monetary(string='Efecto en la diferencia')
    abs_effect = fields.Monetary(compute='_compute_abs_effect', store=True)
    account_code = fields.Char(string='Cuenta')
    label = fields.Char(string='Glosa')
    note = fields.Text(string='Observación')
    account_note = fields.Char(string='Cuenta distinta', index='btree_not_null',
                               help='Observación automática: las empresas usan cuentas de distinta familia '
                                    '(p.ej. 12 contra 46).')
    action_hint = fields.Text(string='Qué hacer')
    line_count = fields.Integer(string='Apuntes (cantidad)')
    review_key = fields.Char(string='Huella', index=True)
    review_id = fields.Many2one('ic.reconciliation.review', string='Revisión', ondelete='set null')
    review_comment = fields.Text(related='review_id.comment', string='Comentario de la revisión')
    review_user_id = fields.Many2one(related='review_id.user_id', string='Revisado por')
    review_date = fields.Datetime(related='review_id.date', string='Revisado el')
    manual_match_id = fields.Many2one('ic.reconciliation.manual.match', string='Emparejamiento manual', ondelete='set null')
    is_pending = fields.Boolean(string='Es diferencia', readonly=True,
                                help='Diferencia real según la regla (no conciliada ni explicada).')
    status = fields.Selection(
        selection=[('pending', 'Pendiente'), ('reviewed', 'Revisado'), ('matched', 'Conciliado'),
                   ('manual', 'Conciliado manual')],
        compute='_compute_status', store=True, string='Estado')
    is_new = fields.Boolean(string='Nuevo', help='Pendiente que no estaba en la ejecución anterior.')
    original_category = fields.Selection(
        CATEGORY_SELECTION, string='Categoría antes de emparejar',
        help='Categoría a la que vuelve la línea si se deshace el emparejamiento manual.')
    original_note = fields.Text(string='Observación antes de emparejar')
    suggested_line_id = fields.Many2one('ic.reconciliation.line', string='Posible contraparte', ondelete='set null',
                                        help='Sugerencia (no se emparejó sola): revisar y, si corresponde, emparejar.')
    suggestion_note = fields.Char(string='Sugerencia')
    is_partial_advance = fields.Boolean(
        string='Anticipo aplicado parcialmente',
        help='Anticipo o préstamo registrado en las dos empresas cuyas sumas no cuadran: revisar a mano.')

    @api.depends('move_name', 'company_id')
    def _compute_display_name(self):
        # La posible contraparte (Many2one a otra línea) se muestra por su asiento.
        for line in self:
            line.display_name = f"{line.move_name or _('Sin asiento')} ({line.company_id.name})"

    @api.depends('effect_pen')
    def _compute_abs_effect(self):
        for line in self:
            line.abs_effect = abs(line.effect_pen)

    def _compute_rule_name(self):
        names = dict(RULES)
        for line in self:
            if line.category == 'prior_period':
                line.rule_name = RULE_PRIOR
            else:
                line.rule_name = f"{line.rule}. {names.get(line.rule, '')}" if line.rule else ''

    @api.depends('category', 'is_pending', 'review_id', 'manual_match_id')
    def _compute_status(self):
        for line in self:
            if line.category == 'manual_match':
                line.status = 'manual'
            elif not line.is_pending:
                line.status = 'matched'
            elif line.review_id:
                line.status = 'reviewed'
            else:
                line.status = 'pending'

    # ------------------------------------------------------------------ #
    # Abrir documentos
    # ------------------------------------------------------------------ #

    def _open_move(self, move, company):
        if not move:
            raise UserError(_('Esta línea no tiene documento en esa empresa.'))
        if company not in self.env.user.company_ids:
            raise UserError(_('No tiene acceso a la empresa %s.', company.name))
        allowed = list(dict.fromkeys(self.env.context.get('allowed_company_ids', self.env.companies.ids) + [company.id]))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'allowed_company_ids': allowed},
        }

    def action_open_document(self):
        self.ensure_one()
        return self._open_move(self.move_id, self.company_id)

    def action_open_counterpart(self):
        self.ensure_one()
        return self._open_move(self.counterpart_move_id, self.counterpart_company_id)

    def action_open_move_lines(self):
        self.ensure_one()
        lines = self.move_line_ids | self.counterpart_line_ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Apuntes'),
            'res_model': 'account.move.line',
            'domain': [('id', 'in', lines.ids)],
            'view_mode': 'list,form',
            'context': {'allowed_company_ids': list(set(self.env.companies.ids) | set(lines.company_id.ids) & set(self.env.user.company_ids.ids))},
        }

    # ------------------------------------------------------------------ #
    # Revisión y emparejamiento manual
    # ------------------------------------------------------------------ #

    def _check_manager(self):
        if not self.env.user.has_group('empiria_intercompany_reconciliation.group_ic_reconciliation_manager'):
            raise UserError(_('Solo el grupo Conciliación IC / Responsable puede hacer esta acción.'))

    def action_mark_reviewed(self):
        self._check_manager()
        lines = self.filtered(lambda line: line.status == 'pending')
        if not lines:
            raise UserError(_('Elija líneas pendientes para marcarlas como revisadas.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ic.reconciliation.review.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_ids': [(6, 0, lines.ids)]},
        }

    def action_undo_review(self):
        self._check_manager()
        reviews = self.review_id
        if not reviews:
            raise UserError(_('Las líneas elegidas no están revisadas.'))
        reviews.write({'active': False})
        lines = self.search([('review_id', 'in', reviews.ids)])
        lines.write({'review_id': False})
        lines.run_id._refresh_counters()
        return True

    def _check_match_lines(self):
        """Las líneas a emparejar deben ser contraparte entre sí: del mismo par de
        empresas, o de una compensación entre tres empresas relacionadas entre sí."""
        if len(self.run_id) > 1:
            raise UserError(_('Elija líneas de una misma ejecución.'))
        if len(self.company_id) < 2:
            raise UserError(_('Elija al menos una línea de cada empresa del par (o de la tercera, si es una compensación).'))
        companies = self.company_id | self.counterpart_company_id
        pairs = {frozenset((line.company_id.id, line.counterpart_company_id.id)) for line in self}
        if len(companies) == 2 or (len(companies) == 3 and self.company_id == companies and len(pairs) >= 2):
            return
        raise UserError(_(
            'Las líneas elegidas no son contraparte entre sí:\n%(pairs)s\n\nSolo se puede emparejar dentro de un mismo '
            'par de empresas, o en una compensación entre tres empresas en la que cada una tiene una línea.',
            pairs='\n'.join(f"- {line.move_name or line.display_name}: {line.company_id.name} ↔ "
                             f"{line.counterpart_company_id.name}" for line in self)))

    def action_manual_match(self):
        self._check_manager()
        lines = self.filtered(lambda line: line.status in ('pending', 'reviewed'))
        lines._check_match_lines()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ic.reconciliation.match.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_line_ids': [(6, 0, lines.ids)]},
        }

    def action_undo_manual_match(self):
        """Archiva el emparejamiento y devuelve sus líneas (de todas las ejecuciones)
        a pendiente, con la categoría que tenían antes de emparejar."""
        self._check_manager()
        matches = self.manual_match_id
        if not matches:
            raise UserError(_('Las líneas elegidas no tienen un emparejamiento manual.'))
        matches.write({'active': False})
        lines = self.search([('manual_match_id', 'in', matches.ids)])
        note = _('Emparejamiento deshecho por %s.', self.env.user.name)
        for line in lines:
            category = line.original_category or 'manual_entry'
            line.write({
                'category': category,
                # Solo se empareja a mano lo pendiente o revisado: vuelve a ser diferencia.
                'is_pending': True,
                'manual_match_id': False,
                'note': ' '.join(filter(None, [line.original_note, note])) if line.original_category else _(
                    '%s Genere una nueva ejecución para ver cada documento con su categoría.', note),
                'action_hint': CATEGORY_HINTS.get(category, ''),
                'original_category': False,
                'original_note': False,
            })
        lines.run_id._refresh_counters()
        return True

    def action_match_suggestion(self):
        """Abre el asistente de emparejar a mano con la línea y su posible contraparte."""
        self.ensure_one()
        if not self.suggested_line_id:
            raise UserError(_('Esta línea no tiene una posible contraparte sugerida.'))
        return (self | self.suggested_line_id).action_manual_match()
