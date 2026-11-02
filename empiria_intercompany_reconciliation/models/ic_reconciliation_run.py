import logging
import re
import time
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import date_utils

from ..engine import CATEGORY_LABELS, LOAN_PREFIXES, Engine, block_code, normalize_document

_logger = logging.getLogger(__name__)

BATCH = 2000


class IcReconciliationRun(models.Model):
    _name = 'ic.reconciliation.run'
    _description = 'Ejecución de la conciliación intercompany'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, id desc'

    name = fields.Char(required=True, tracking=True)
    date_from = fields.Date(
        string='Desde', help='Inicio del periodo (opcional). Vacío: desde el inicio. Las diferencias de documentos '
                             'anteriores se resumen en una línea por par.')
    date_to = fields.Date(string='Hasta (fecha de corte)', required=True, default=fields.Date.context_today)
    company_ids = fields.Many2many(
        comodel_name='res.company', relation='ic_reconciliation_run_company_rel', string='Empresas')
    include_balanced = fields.Boolean(string='Incluir pares que cuadran')
    origin = fields.Selection(
        selection=[('manual', 'Manual'), ('cron', 'Automática')], default='manual', required=True, string='Origen')
    state = fields.Selection(
        selection=[('draft', 'Borrador'), ('done', 'Calculado')], default='draft', required=True, tracking=True)
    user_id = fields.Many2one('res.users', string='Generado por', default=lambda self: self.env.user)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.ref('base.PEN', raise_if_not_found=False)
                                  or self.env.company.currency_id)
    pair_ids = fields.One2many('ic.reconciliation.pair', 'run_id', string='Pares')
    line_ids = fields.One2many('ic.reconciliation.line', 'run_id', string='Detalle')
    previous_run_id = fields.Many2one('ic.reconciliation.run', string='Ejecución anterior', readonly=True)
    pending_pair_count = fields.Integer(string='Pares por conciliar', readonly=True)
    pending_line_count = fields.Integer(string='Líneas pendientes', readonly=True)
    reviewed_line_count = fields.Integer(string='Líneas revisadas', readonly=True)
    new_line_count = fields.Integer(string='Pendientes nuevos', readonly=True,
                                    help='Pendientes que no estaban en la ejecución anterior.')
    resolved_line_count = fields.Integer(string='Resueltos', readonly=True,
                                         help='Pendientes de la ejecución anterior que ya no aparecen.')
    control_ok = fields.Boolean(string='Control en 0', readonly=True)
    control_total = fields.Monetary(string='Control', readonly=True)
    duration = fields.Float(string='Duración (s)', readonly=True)
    is_month_end = fields.Boolean(compute='_compute_is_month_end', store=True)
    is_last = fields.Boolean(string='Última ejecución', readonly=True, copy=False)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for run in self:
            if run.date_from and run.date_from > run.date_to:
                raise ValidationError(_('La fecha desde no puede ser posterior a la fecha hasta.'))

    @api.model
    def _run_name(self, date_from, date_to):
        if date_from:
            return _('Conciliación IC del %(from)s al %(to)s',
                     **{'from': date_from.strftime('%d/%m/%Y'), 'to': date_to.strftime('%d/%m/%Y')})
        return _('Conciliación IC al %s', date_to.strftime('%d/%m/%Y'))

    @api.depends('date_to')
    def _compute_is_month_end(self):
        for run in self:
            run.is_month_end = bool(run.date_to) and run.date_to == date_utils.end_of(run.date_to, 'month')

    # ------------------------------------------------------------------ #
    # Cálculo
    # ------------------------------------------------------------------ #

    def action_compute(self):
        for run in self:
            run._compute_reconciliation()
        return self.action_open_pairs() if len(self) == 1 else True

    def _compute_reconciliation(self):
        self.ensure_one()
        started = time.time()
        config = self.env['ic.reconciliation.config'].get_config()
        companies = (self.company_ids or config._get_companies()).sudo()
        if len(companies) < 2:
            raise UserError(_('Elija al menos dos empresas del grupo (Configuración de la conciliación intercompany).'))
        collector = IcDataCollector(self.env, config, companies, self.date_to)
        rows = collector.collect()
        manual_matches = [
            {'id': match.id, 'line_ids': set((match.line_ids_a | match.line_ids_b).ids),
             'reason': match._reason_text()}
            for match in self.env['ic.reconciliation.manual.match'].sudo().search([])
        ]
        engine = Engine(
            collector.company_info(), rows, params=config._engine_params(),
            receiver_lookup=collector.receiver_lookup, manual_matches=manual_matches,
            company_names={company.id: company.name for company in companies},
            company_keywords=config._keywords_by_company(), date_from=self.date_from,
        )
        pairs, details = engine.run()
        self._store(pairs, details, rows)
        self.search([('is_last', '=', True), ('id', '!=', self.id)]).sudo().write({'is_last': False})
        self.write({'state': 'done', 'duration': round(time.time() - started, 1), 'is_last': True})
        _logger.info('Conciliación IC %s: %s apuntes, %s pares, %s líneas en %.1fs',
                     self.name, len(rows), len(pairs), len(details), time.time() - started)

    def _store(self, pairs, details, rows):
        self.ensure_one()
        self.sudo().line_ids.unlink()
        self.sudo().pair_ids.unlink()
        Pair = self.env['ic.reconciliation.pair'].sudo()
        Line = self.env['ic.reconciliation.line'].sudo()
        reviews = {review.key: review for review in self.env['ic.reconciliation.review'].sudo().search([])}
        previous = self.search([('state', '=', 'done'), ('id', '!=', self.id), ('date_to', '<=', self.date_to),
                                ('date_from', '=', self.date_from)], limit=1)
        previous_keys = set(previous.line_ids.filtered('is_pending').mapped('review_key')) if previous else set()

        # Total del par: suma de los dos bloques (A cobra y B cobra).
        pair_totals = defaultdict(float)
        for (company_a, company_b, _creditor), values in pairs.items():
            pair_totals[(company_a, company_b)] += values['difference']
        pair_records = {}
        for key, values in sorted(pairs.items(), key=lambda item: -abs(item[1]['difference'])):
            if not self.include_balanced and abs(values['difference']) < 0.005 and not values['pending_count']:
                continue
            company_a, company_b, _creditor = key
            vals = {
                'run_id': self.id, 'company_a_id': company_a, 'company_b_id': company_b, 'block': block_code(key),
                'total_difference': round(pair_totals[(company_a, company_b)], 2),
                'balance_a': values['balance_a'], 'balance_b': values['balance_b'],
                'difference': values['difference'], 'control': values['control'],
                'opening_a': values['opening_a'], 'opening_b': values['opening_b'],
                'opening_difference': values['opening_difference'],
                'matched_count': values['matched_count'],
            }
            for category, amount in values['by_category'].items():
                vals[f'amount_{category}'] = amount
            pair_records[key] = Pair.create(vals)

        currencies = {currency.name: currency.id
                      for currency in self.env['res.currency'].with_context(active_test=False).search([])}
        line_vals = []
        stored_details = []
        current_keys = set()
        for detail in details:
            pair = pair_records.get(detail['pair_key'])
            if not pair:
                continue
            stored_details.append(detail)
            review = reviews.get(detail['review_key'])
            pending = detail['pending']
            if pending:
                current_keys.add(detail['review_key'])
            line_vals.append({
                'run_id': self.id,
                'pair_id': pair.id,
                'category': detail['category'],
                'rule': int(detail['rule']),
                'company_id': detail['company'],
                'counterpart_company_id': detail['counterpart_company'],
                'move_id': detail['move_ids'][0] if detail['move_ids'] else False,
                'move_line_ids': [(6, 0, detail['line_ids'])] if not detail.get('aggregated') else [],
                'counterpart_move_id': detail['counterpart_move_ids'][0] if detail['counterpart_move_ids'] else False,
                'counterpart_line_ids': [(6, 0, detail['counterpart_line_ids'])],
                'move_name': detail['move_name'],
                'counterpart_move_name': detail['counterpart_move_name'],
                'doc_type': detail['doc_type'],
                'doc_number': detail['doc_number'],
                'date': detail['date'],
                'counterpart_date': detail['counterpart_date'],
                'line_currency_id': currencies.get(detail['currency'], False),
                'amount_currency': detail['amount_currency'],
                'amount_pen': detail['amount_pen'],
                'counterpart_currency_id': currencies.get(detail['counterpart_currency'], False),
                'counterpart_amount_currency': detail['counterpart_amount_currency'],
                'counterpart_amount_pen': detail['counterpart_amount_pen'],
                'effect_pen': detail['effect_pen'],
                'account_code': detail['account_code'],
                'label': detail['label'],
                'note': detail['note'],
                'account_note': detail['account_note'],
                'is_pending': pending,
                'action_hint': detail['action_hint'],
                'review_key': detail['review_key'],
                'review_id': review.id if review else False,
                'manual_match_id': detail.get('manual_match_id') or False,
                'is_new': bool(previous) and pending and detail['review_key'] not in previous_keys,
                'line_count': detail['line_count'],
                'original_category': detail.get('original_category') or False,
                'suggestion_note': detail.get('suggestion_note') or False,
                'is_partial_advance': detail.get('partial_advance', False),
            })
        lines = Line.create(line_vals)
        # Sugerencias: enlazar con la línea del grupo sugerido.
        by_group = {}
        for detail, line in zip(stored_details, lines):
            by_group.setdefault(detail.get('group_ref'), line)
        for detail, line in zip(stored_details, lines):
            suggested = by_group.get(detail.get('suggestion_ref')) if detail.get('suggestion_ref') else None
            if suggested and suggested != line:
                line.suggested_line_id = suggested

        for pair in pair_records.values():
            pending_lines = pair.line_ids.filtered('is_pending')
            pair.write({
                'pending_count': len(pending_lines.filtered(lambda line: not line.review_id)),
                'reviewed_count': len(pending_lines.filtered('review_id')),
            })
        pairs_records = self.pair_ids
        self.write({
            'previous_run_id': previous.id,
            'pending_pair_count': len(pairs_records.filtered(lambda pair: pair.state != 'balanced')),
            'pending_line_count': sum(pairs_records.mapped('pending_count')),
            'reviewed_line_count': sum(pairs_records.mapped('reviewed_count')),
            'new_line_count': len(self.line_ids.filtered('is_new')),
            'resolved_line_count': len(previous_keys - current_keys) if previous else 0,
            'control_total': round(sum(abs(value['control']) for value in pairs.values()), 2),
            'control_ok': all(abs(value['control']) < 0.005 for value in pairs.values()),
        })

    def _refresh_counters(self):
        """Recalcula importes por categoría y contadores desde el detalle, tras
        marcar revisado, emparejar a mano o deshacer (sin volver a calcular)."""
        categories = [key for key in CATEGORY_LABELS]
        for run in self:
            for pair in run.pair_ids:
                by_category = defaultdict(float)
                for line in pair.line_ids:
                    by_category[line.category] += line.effect_pen
                vals = {f'amount_{category}': round(by_category.get(category, 0.0), 2) for category in categories}
                pending = pair.line_ids.filtered('is_pending')
                vals.update({
                    'pending_count': len(pending.filtered(lambda line: not line.review_id)),
                    'reviewed_count': len(pending.filtered('review_id')),
                    'control': round(pair.difference - sum(by_category.values()), 2),
                })
                pair.write(vals)
            run.write({
                'pending_pair_count': len(run.pair_ids.filtered(lambda pair: pair.state != 'balanced')),
                'pending_line_count': sum(run.pair_ids.mapped('pending_count')),
                'reviewed_line_count': sum(run.pair_ids.mapped('reviewed_count')),
                'control_total': round(sum(abs(control) for control in run.pair_ids.mapped('control')), 2),
                'control_ok': all(abs(control) < 0.005 for control in run.pair_ids.mapped('control')),
            })

    # ------------------------------------------------------------------ #
    # Acciones
    # ------------------------------------------------------------------ #

    def action_open_pairs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('empiria_intercompany_reconciliation.action_ic_reconciliation_pair')
        action['domain'] = [('run_id', '=', self.id)]
        action['context'] = {'search_default_filter_pending': 1}
        action['name'] = self.name
        return action

    def action_open_lines(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('empiria_intercompany_reconciliation.action_ic_reconciliation_line')
        action['domain'] = [('run_id', '=', self.id)]
        action['context'] = {'search_default_filter_pending': 1, 'search_default_group_category': 1}
        return action

    def action_open_new_lines(self):
        action = self.action_open_lines()
        action['domain'] = [('run_id', '=', self.id), ('is_new', '=', True)]
        return action

    def action_export_xlsx(self):
        self.ensure_one()
        from ..report.ic_reconciliation_xlsx import build_workbook
        content = build_workbook(self)
        suffix = '' if self.control_ok else '_NO_DEFINITIVA'
        period = f"{self.date_from:%d-%m-%Y}_al_" if self.date_from else ''
        filename = f"Conciliacion_Intercompany_documentos_{period}{self.date_to:%d-%m-%Y}{suffix}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename, 'datas': content, 'res_model': self._name, 'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{attachment.id}?download=true', 'target': 'self'}

    # ------------------------------------------------------------------ #
    # Ejecución diaria
    # ------------------------------------------------------------------ #

    @api.model
    def _cron_generate(self):
        config = self.env['ic.reconciliation.config'].get_config()
        companies = config._get_companies()
        if len(companies) < 2:
            # Sin al menos dos empresas no hay pares: se deja constancia en el log del cron.
            raise UserError(_('Conciliación IC: no hay al menos dos empresas con RUC para conciliar. Elija las empresas '
                              'del grupo en Configuración de la conciliación intercompany.'))
        today = fields.Date.context_today(self)
        date_from = config._cron_date_from(today)
        run = self.create({
            'name': self._run_name(date_from, today),
            'date_from': date_from,
            'date_to': today, 'origin': 'cron', 'company_ids': [(6, 0, companies.ids)],
            'include_balanced': True,
        })
        warnings = []
        if not config.company_ids:
            warnings.append(_('La configuración no tiene empresas elegidas: se usaron todas las empresas con RUC (%s).',
                              ', '.join(companies.mapped('name'))))
        if not config.responsible_user_id:
            warnings.append(_('La configuración no tiene responsable: nadie recibe el aviso de pendientes nuevos o '
                              'control distinto de 0. Elíjalo en Configuración de la conciliación intercompany.'))
        for warning in warnings:
            _logger.warning('Conciliación IC: %s', warning)
            run.message_post(body=warning)
        run._compute_reconciliation()
        run._notify_responsible(config)
        self._cleanup_runs(config)
        return run

    def _notify_responsible(self, config):
        self.ensure_one()
        user = config.responsible_user_id
        if not user or (self.control_ok and not self.new_line_count):
            return
        problems = []
        if self.new_line_count:
            problems.append(_('%s pendientes nuevos', self.new_line_count))
        if not self.control_ok:
            problems.append(_('control distinto de 0 en algún par'))
        self.activity_schedule(
            'mail.mail_activity_data_todo', user_id=user.id,
            summary=_('Conciliación IC: %s', ', '.join(problems)),
            note=_('Revise la ejecución %s: %s pares por conciliar, %s pendientes (%s nuevos).',
                   self.name, self.pending_pair_count, self.pending_line_count, self.new_line_count),
        )

    @api.model
    def _cleanup_runs(self, config):
        runs = self.search([('origin', '=', 'cron'), ('is_month_end', '=', False)], order='date_to desc, id desc')
        old = runs[max(config.keep_runs, 1):]
        if old:
            old.sudo().unlink()


class IcDataCollector:
    """Lee con el ORM (sudo controlado) los apuntes publicados del universo y los
    deja en el formato del motor."""

    def __init__(self, env, config, companies, date_to):
        self.env = env
        self.config = config
        self.companies = companies
        self.date_to = date_to
        vat_to_company = {company.vat: company.id for company in companies if company.vat}
        partners = env['res.partner'].sudo().with_context(active_test=False).search([('vat', 'in', list(vat_to_company))])
        self.partner_company = {partner.id: vat_to_company[partner.vat] for partner in partners}
        self.vat_to_company = vat_to_company
        self._purchase_index = {}

    def company_info(self):
        info = {}
        for company in self.companies:
            first = self.env['account.move.line'].sudo().search(
                [('company_id', '=', company.id), ('parent_state', '=', 'posted')], order='date asc', limit=1)
            info[company.id] = {'name': company.name, 'legal_name': company.name, 'first_date': first.date or None}
        return info

    def fx_journal_ids(self, company):
        journals = self.config.fx_journal_ids.filtered(lambda journal: journal.company_id == company)
        return set((journals or company.currency_exchange_journal_id).ids)

    def collect(self):
        rows = []
        for company in self.companies:
            rows += self._collect_company(company)
        return rows

    def _collect_company(self, company):
        env = self.env(context={**self.env.context, 'allowed_company_ids': [company.id]}, su=True)
        Account = env['account.account'].with_company(company)
        accounts = {}
        for side in ('receivable', 'payable'):
            for prefix in self.config._prefixes(side):
                for account in Account.search([('code', '=like', f'{prefix}%'), ('company_ids', 'in', company.id)]):
                    family = 'loan' if account.code.startswith(LOAN_PREFIXES) else 'commercial'
                    accounts.setdefault(account.id, (side, family, account.code))
        if not accounts:
            return []
        domain = [
            ('company_id', '=', company.id), ('parent_state', '=', 'posted'), ('date', '<=', self.date_to),
            ('account_id', 'in', list(accounts)), ('partner_id', 'in', list(self.partner_company)),
        ]
        AML = env['account.move.line']
        fields_list = ['move_id', 'date', 'account_id', 'partner_id', 'balance', 'amount_currency',
                       'currency_id', 'name', 'ref', 'journal_id']
        lines = []
        offset = 0
        while True:
            batch = AML.search_read(domain, fields_list, offset=offset, limit=BATCH, order='id')
            lines += batch
            offset += BATCH
            if len(batch) < BATCH:
                break
        move_info = self._move_info(env, {line['move_id'][0] for line in lines})
        journals = {journal.id: journal for journal in env['account.journal'].browse({l['journal_id'][0] for l in lines})}
        fx_journals = self.fx_journal_ids(company)
        currencies = {currency.id: currency.name for currency in env['res.currency'].with_context(active_test=False).search([])}
        rows = []
        for line in lines:
            side, family, code = accounts[line['account_id'][0]]
            partner_company = self.partner_company[line['partner_id'][0]]
            move = move_info[line['move_id'][0]]
            journal = journals[line['journal_id'][0]]
            rows.append({
                'id': line['id'], 'company': company.id, 'partner_company': partner_company,
                # Bloque = la empresa que cobra.
                'block': company.id if side == 'receivable' else partner_company,
                'family': family, 'account_code': code,
                'journal_type': journal.type, 'journal_code': journal.code or '', 'journal_name': journal.name or '',
                'is_fx_journal': journal.id in fx_journals,
                'move_id': line['move_id'][0], 'move_name': move['name'], 'move_type': move['move_type'],
                'doc_kind': move['doc_kind'], 'doc_serie': move['doc_serie'], 'doc_number': move['doc_number'],
                'doc_type_code': move['doc_type_code'], 'doc_total': move['amount_total'],
                'move_currency': move['currency'], 'date': line['date'],
                'currency': currencies.get(line['currency_id'][0]) if line['currency_id'] else company.currency_id.name,
                'amount_currency': line['amount_currency'], 'balance': line['balance'],
                'label': line['name'] or '', 'ref': line['ref'] or '',
                'reversed_move_id': move['reversed_move_id'],
            })
        return rows

    def _move_info(self, env, move_ids):
        info = {}
        move_ids = sorted(move_ids)
        Move = env['account.move']
        for start in range(0, len(move_ids), BATCH):
            for move in Move.browse(move_ids[start:start + BATCH]):
                doc_type_code = move.l10n_latam_document_type_id.code or ''
                kind = None
                if move.move_type in ('out_invoice', 'in_invoice'):
                    kind = 'debit' if doc_type_code == '08' else 'invoice'
                elif move.move_type in ('out_refund', 'in_refund'):
                    kind = 'refund'
                # La venta toma el número del comprobante y la compra la Referencia.
                number = (move.l10n_latam_document_number or move.name) if move.move_type.startswith('out_') else move.ref
                serie, doc_number = normalize_document(number) if kind else (None, None)
                info[move.id] = {
                    'name': move.name, 'move_type': move.move_type, 'doc_kind': kind,
                    'doc_serie': serie, 'doc_number': doc_number, 'doc_type_code': doc_type_code,
                    'amount_total': move.amount_total, 'currency': move.currency_id.name,
                    'reversed_move_id': move.reversed_entry_id.id or None,
                }
            Move.invalidate_model()
        return info

    def receiver_lookup(self, company, kind, serie, number):
        """Regla 7: el comprobante en la empresa receptora en cualquier estado."""
        if company not in self._purchase_index:
            env = self.env(context={**self.env.context, 'allowed_company_ids': [company]}, su=True)
            index = defaultdict(list)
            for move in env['account.move'].search_read(
                    [('company_id', '=', company), ('move_type', 'in', ('in_invoice', 'in_refund'))],
                    ['name', 'ref', 'state', 'partner_id', 'move_type']):
                doc_serie, doc_number = normalize_document(move['ref'])
                if doc_number:
                    index[(doc_serie, doc_number)].append(move)
            vat_by_partner = {}
            partner_ids = {m['partner_id'][0] for moves in index.values() for m in moves if m['partner_id']}
            for partner in env['res.partner'].with_context(active_test=False).browse(partner_ids):
                vat_by_partner[partner.id] = partner.vat
            self._purchase_index[company] = (index, vat_by_partner)
        index, vat_by_partner = self._purchase_index[company]
        wanted = 'refund' if kind == 'refund' else 'invoice'
        found = []
        for move in index.get((serie, number), []):
            if ('refund' if move['move_type'] == 'in_refund' else 'invoice') != wanted:
                continue
            partner_id = move['partner_id'] and move['partner_id'][0]
            found.append({
                'move_name': move['name'], 'state': move['state'],
                'partner_company': self.vat_to_company.get(vat_by_partner.get(partner_id)),
                'partner_name': move['partner_id'] and move['partner_id'][1],
            })
        return found
