from datetime import datetime, time
from decimal import Decimal

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round, format_date

ZERO = Decimal('0')
WAC_FETCH_SIZE = 2000


def _to_decimal(value):
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class StockKardexCostAudit(models.Model):
    _name = 'stock.kardex.cost.audit'
    _description = 'Kardex Cost Audit (WAC vs Recorded)'
    _check_company_auto = True
    _order = 'create_date desc, id desc'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
    )
    date_from = fields.Date(
        string='Start Date',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
        help='Movements within this period are audited. Earlier layers are still '
             'read to build the opening balance.',
    )
    date_to = fields.Date(
        string='End Date',
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    date_basis = fields.Selection(
        selection=[
            ('accounting', 'Accounting Date'),
            ('creation', 'Creation Date'),
        ],
        string='Date Basis',
        default='accounting',
        required=True,
        help='Date used to order layers when recomputing the weighted average '
             'cost. Use the accounting date to match the valued inventory ledger.',
    )
    only_differences = fields.Boolean(
        string='Only Differences',
        default=True,
        help='If enabled, only products whose recorded cost differs from the '
             'recomputed weighted average are listed.',
    )
    filter_product_ids = fields.Many2many(
        comodel_name='product.product',
        relation='stock_kardex_cost_audit_product_rel',
        column1='audit_id',
        column2='product_id',
        string='Filter by Products',
    )
    filter_category_ids = fields.Many2many(
        comodel_name='product.category',
        relation='stock_kardex_cost_audit_category_rel',
        column1='audit_id',
        column2='category_id',
        string='Filter by Categories',
    )
    line_ids = fields.One2many(
        comodel_name='stock.kardex.cost.audit.line',
        inverse_name='audit_id',
        string='Results',
        readonly=True,
    )
    computed = fields.Boolean(
        default=False,
        help='Technical flag: set once the audit has been run.',
    )
    line_count = fields.Integer(
        string='Audited Products',
        compute='_compute_summary',
    )
    diff_count = fields.Integer(
        string='Products with Differences',
        compute='_compute_summary',
    )
    revalued_count = fields.Integer(
        string='Revalued',
        compute='_compute_summary',
    )
    regularized_count = fields.Integer(
        string='Regularized',
        compute='_compute_summary',
    )
    pending_count = fields.Integer(
        string='Pending Correction',
        compute='_compute_summary',
        help='Products with a difference that have not been revalued yet.',
    )
    to_regularize_count = fields.Integer(
        string='Pending Entries',
        compute='_compute_summary',
        help='Products already revalued whose accounting entry is still missing.',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Parameters'),
            ('to_correct', 'Differences Found'),
            ('to_regularize', 'Valuation Aligned'),
            ('done', 'Done'),
        ],
        string='Status',
        compute='_compute_state',
    )

    @api.depends('computed', 'diff_count', 'pending_count', 'to_regularize_count')
    def _compute_state(self):
        for rec in self:
            if not rec.computed:
                rec.state = 'draft'
            elif rec.pending_count:
                rec.state = 'to_correct'
            elif rec.to_regularize_count:
                rec.state = 'to_regularize'
            else:
                rec.state = 'done'

    # --- Regularization options ---
    correction_date = fields.Date(
        string='Correction Date',
        help='Accounting date used for the revaluation layers and the '
             'correction journal entries. Defaults to the end of the period.',
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Correction Journal',
        check_company=True,
        help='Journal used for the correction entries. Leave empty to use the '
             'stock journal configured on each product category.',
    )
    counterpart_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Counterpart Account',
        domain="[('deprecated', '=', False)]",
        check_company=True,
        help='Counterpart account for the difference. Leave empty to use the '
             'expense (COGS) account of each product.',
    )

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_display_name(self):
        for rec in self:
            if rec.date_from and rec.date_to:
                rec.display_name = _(
                    'Kardex Cost Audit  %(date_from)s → %(date_to)s',
                    date_from=format_date(rec.env, rec.date_from),
                    date_to=format_date(rec.env, rec.date_to),
                )
            else:
                rec.display_name = _('Kardex Cost Audit')

    @api.depends('line_ids', 'line_ids.has_difference', 'line_ids.correction_state')
    def _compute_summary(self):
        for rec in self:
            lines = rec.line_ids
            diff_lines = lines.filtered('has_difference')
            rec.line_count = len(lines)
            rec.diff_count = len(diff_lines)
            rec.revalued_count = len(lines.filtered(
                lambda l: l.correction_state in ('revalued', 'regularized')))
            rec.regularized_count = len(lines.filtered(
                lambda l: l.correction_state == 'regularized'))
            rec.pending_count = len(diff_lines.filtered(
                lambda l: l.correction_state == 'pending'))
            rec.to_regularize_count = len(diff_lines.filtered(
                lambda l: l.correction_state == 'revalued'))

    @api.onchange('date_to')
    def _onchange_date_to_correction(self):
        for rec in self:
            if rec.date_to and (not rec.correction_date or rec.correction_date < rec.date_from):
                rec.correction_date = rec.date_to

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(
                    _('The start date cannot be later than the end date.')
                )

    def _get_date_field_sql(self):
        if self.date_basis == 'creation':
            return 'svl.create_date'
        return 'COALESCE(svl.accounting_date, svl.create_date)'

    def _resolve_product_ids(self):
        products = self.filter_product_ids
        if self.filter_category_ids:
            all_cats = self.env['product.category'].search([
                ('id', 'child_of', self.filter_category_ids.ids)
            ])
            category_products = self.env['product.product'].search([
                ('product_tmpl_id.categ_id', 'in', all_cats.ids),
                ('product_tmpl_id.is_storable', '=', True),
            ])
            if products:
                products = products & category_products
            else:
                products = category_products
        return products.ids

    def _build_audit_query(self):
        date_field = self._get_date_field_sql()
        params = [self.date_from, self.date_to, self.date_to, self.company_id.id]
        product_ids = self._resolve_product_ids()
        product_filter = ''
        if product_ids:
            product_filter = 'AND svl.product_id IN %s'
            params.append(tuple(product_ids))
        elif self.filter_product_ids or self.filter_category_ids:
            product_filter = 'AND svl.product_id IN %s'
            params.append((0,))
        query = f"""
            SELECT
                svl.product_id,
                svl.quantity,
                svl.unit_cost,
                svl.value,
                ({date_field} >= %s AND {date_field} <= %s) AS in_period,
                COALESCE(svl.kardex_cost_correction, false) AS is_correction
            FROM stock_valuation_layer svl
            JOIN product_product pp ON pp.id = svl.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE {date_field} <= %s
              AND svl.company_id = %s
              AND pt.is_storable = true
              AND NOT EXISTS (
                  SELECT 1 FROM stock_move sm
                  WHERE sm.id = svl.stock_move_id AND sm.state != 'done'
              )
              {product_filter}
            ORDER BY svl.product_id, {date_field}, svl.id
        """
        return query, params

    def _compute_audit_rows(self):
        query, params = self._build_audit_query()
        self.env.cr.execute(query, params)
        results = []
        current_pid = None
        state = None

        def flush(pid, st):
            if pid is None or st is None:
                return
            if not st['has_period_activity']:
                return
            results.append({
                'product_id': pid,
                'qty_out': st['qty_out'],
                'cogs_recorded': st['cogs_recorded'],
                'cogs_wac': st['cogs_wac'],
                'qty_balance': st['qty_acum'],
                'value_recorded': st['value_recorded'],
                'value_wac': st['value_acum'],
            })

        while True:
            rows = self.env.cr.fetchmany(WAC_FETCH_SIZE)
            if not rows:
                break
            for product_id, quantity, unit_cost, value, in_period, is_correction in rows:
                if product_id != current_pid:
                    flush(current_pid, state)
                    current_pid = product_id
                    state = {
                        'qty_acum': ZERO,
                        'value_acum': ZERO,
                        'value_recorded': ZERO,
                        'qty_out': ZERO,
                        'cogs_recorded': ZERO,
                        'cogs_wac': ZERO,
                        'has_period_activity': False,
                    }
                qty = _to_decimal(quantity)
                cost = _to_decimal(unit_cost)
                val = _to_decimal(value)
                # The recorded balance always reflects every layer, including the
                # manual corrections we post to align it with the kardex.
                state['value_recorded'] += val
                # Correction layers (quantity 0) are deliberately kept out of the
                # WAC recomputation so that, once the recorded value matches the
                # WAC, a re-run of the audit reports no difference.
                if is_correction:
                    if in_period:
                        state['has_period_activity'] = True
                    continue
                if qty > 0:
                    state['qty_acum'] += qty
                    state['value_acum'] += qty * cost
                elif qty < 0:
                    abs_qty = -qty
                    wac_prev = state['value_acum'] / state['qty_acum'] if state['qty_acum'] > 0 else ZERO
                    wac_out = abs_qty * wac_prev
                    state['qty_acum'] += qty
                    state['value_acum'] -= wac_out
                    if state['qty_acum'] == ZERO:
                        state['value_acum'] = ZERO
                    if in_period:
                        state['has_period_activity'] = True
                        state['qty_out'] += abs_qty
                        state['cogs_recorded'] += -val
                        state['cogs_wac'] += wac_out
                else:
                    state['value_acum'] += val
                    if in_period:
                        state['has_period_activity'] = True
        flush(current_pid, state)
        return results

    def _filter_auditable_rows(self, rows):
        """Keep only products the recorded-vs-WAC comparison is valid for.

        The audit recomputes a moving (weighted) average, so it only makes
        accounting sense for ``average`` products: in FIFO the recorded value is
        already the correct per-method value, and a standard cost is fixed by
        definition. Lot-valuated products are skipped too because their cost is
        tracked per lot and cannot be audited from a product-level pool.
        """
        if not rows:
            return rows
        pids = [r['product_id'] for r in rows]
        products = self.env['product.product'].browse(pids).with_company(self.company_id)
        eligible = {
            p.id for p in products
            if p.cost_method == 'average' and not p.lot_valuated
        }
        return [r for r in rows if r['product_id'] in eligible]

    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        rows = self._compute_audit_rows()
        rows = self._filter_auditable_rows(rows)
        rounding = self.company_id.currency_id.rounding or 0.01
        epsilon = rounding / 2.0
        commands = []
        for row in rows:
            cogs_diff = float(row['cogs_recorded'] - row['cogs_wac'])
            value_diff = float(row['value_recorded'] - row['value_wac'])
            # The balance value is the correctable metric (and the one a
            # regularization brings back to zero). The COGS gap is kept as a
            # diagnostic of where the divergence entered the period.
            has_diff = abs(value_diff) >= epsilon
            if self.only_differences and not has_diff:
                continue
            commands.append((0, 0, {
                'product_id': row['product_id'],
                'qty_out': float(row['qty_out']),
                'cogs_recorded': float(row['cogs_recorded']),
                'cogs_wac': float(row['cogs_wac']),
                'cogs_difference': cogs_diff,
                'qty_balance': float(row['qty_balance']),
                'value_recorded': float(row['value_recorded']),
                'value_wac': float(row['value_wac']),
                'value_difference': value_diff,
                'has_difference': has_diff,
            }))
        self.line_ids = commands
        self.computed = True

    # ------------------------------------------------------------------
    # Correction helpers
    # ------------------------------------------------------------------
    def _correction_datetime(self):
        """Datetime used to date the correction layers.

        It is pinned to midnight of the correction date so the layer is
        included by the audit query (which compares the accounting date against
        the period bounds as plain dates) and the re-run converges to zero.
        """
        self.ensure_one()
        correction_date = self.correction_date or self.date_to
        return datetime.combine(correction_date, time.min)

    def _correction_description(self):
        self.ensure_one()
        return _(
            'Kardex cost audit correction (%(date_from)s → %(date_to)s)',
            date_from=format_date(self.env, self.date_from),
            date_to=format_date(self.env, self.date_to),
        )

    def _revalue_line(self, line):
        """Create the manual valuation layer that brings the recorded value of
        ``line.product_id`` in line with the recomputed WAC. Returns the created
        layer, or raises ``UserError`` with a human readable reason when the
        product cannot be revalued (caller turns it into a skip)."""
        self.ensure_one()
        currency = self.company_id.currency_id
        product = line.product_id.with_company(self.company_id)
        if product.cost_method != 'average':
            raise UserError(_(
                '%s does not use the average cost method; its valuation cannot '
                'be recomputed from the weighted-average kardex.',
                product.display_name))
        if product.lot_valuated:
            raise UserError(_(
                '%s is valued per lot/serial; correct it from the lot-level '
                'kardex, not from this product-level audit.', product.display_name))
        # recorded - wac is the booked excess; we add its opposite so the
        # recorded valuation lands exactly on the chronological WAC.
        added_value = currency.round(-line.value_difference)
        if currency.is_zero(added_value):
            raise UserError(_(
                '%s has no value difference to correct.', product.display_name))

        # Propagate the recomputed cost to the product itself. The kardex says
        # the period-end unit cost is value_wac / qty_balance; that is the cost
        # future moves must use. We set it (not increment) for maximum precision,
        # rounded to the product price precision, and store it before creating
        # the layer so the cost-change log snapshots the corrected price. This
        # keeps the AVCO invariant value_svl = standard_price * quantity_svl.
        qty_balance = line.qty_balance
        if qty_balance > 0:
            price_precision = self.env['decimal.precision'].precision_get('Product Price')
            new_unit_cost = float_round(
                float(_to_decimal(line.value_wac) / _to_decimal(qty_balance)),
                precision_digits=price_precision,
            )
            product.with_context(disable_auto_svl=True).standard_price = new_unit_cost

        svl = self.env['stock.valuation.layer'].sudo().create({
            'company_id': self.company_id.id,
            'product_id': product.id,
            'description': self._correction_description(),
            'value': added_value,
            'quantity': 0,
            'accounting_date': self._correction_datetime(),
            'kardex_cost_correction': True,
        })

        # Mirror Odoo's native revaluation: spread the value over the layers
        # still holding stock so their remaining_value stays consistent (FIFO
        # candidates / value_svl). Skipped when there is no stock on hand, which
        # is the typical broken case (zero/negative quantity).
        if qty_balance > 0:
            remaining_layers = self.env['stock.valuation.layer'].sudo().search([
                ('product_id', '=', product.id),
                ('company_id', '=', self.company_id.id),
                ('remaining_qty', '>', 0),
            ])
            remaining_qty = sum(remaining_layers.mapped('remaining_qty'))
            remaining_value = added_value
            if remaining_qty and remaining_layers:
                unit = currency.round(added_value / remaining_qty)
                for svl_layer in remaining_layers:
                    if svl_layer == remaining_layers[-1]:
                        taken = remaining_value
                    else:
                        taken = currency.round(unit * svl_layer.remaining_qty)
                    svl_layer.remaining_value += taken
                    remaining_value -= taken
        return svl

    def _regularize_line(self, line):
        """Create the (draft) correction journal entry for an already revalued
        line. Returns the created move, or raises ``UserError`` to be turned
        into a skip by the caller."""
        self.ensure_one()
        currency = self.company_id.currency_id
        svl = line.revaluation_svl_id
        if not svl:
            raise UserError(_(
                '%s has not been revalued yet.', line.product_id.display_name))
        product = line.product_id.with_company(self.company_id)
        if product.valuation != 'real_time':
            raise UserError(_(
                '%s uses a manual inventory valuation; there are no automated '
                'entries to regularize.', product.display_name))
        accounts = product.product_tmpl_id.get_product_accounts()
        valuation_account = accounts.get('stock_valuation')
        counterpart_account = self.counterpart_account_id or accounts.get('expense')
        journal = self.journal_id or accounts.get('stock_journal')
        if not valuation_account or not counterpart_account or not journal:
            raise UserError(_(
                'Missing stock valuation, counterpart (COGS) or journal account '
                'for %s. Configure the product category accounts or fill the '
                'regularization options.', product.display_name))

        amount = currency.round(svl.value)
        if currency.is_zero(amount):
            raise UserError(_(
                '%s has no amount to regularize.', product.display_name))

        if amount > 0:
            debit_account = valuation_account
            credit_account = counterpart_account
        else:
            debit_account = counterpart_account
            credit_account = valuation_account
        amount = abs(amount)

        label = _('Kardex cost regularization: %s', product.display_name)
        move = self.env['account.move'].sudo().create({
            'journal_id': journal.id,
            'company_id': self.company_id.id,
            'move_type': 'entry',
            'date': self.correction_date or self.date_to,
            'ref': self._correction_description(),
            'stock_valuation_layer_ids': [(6, 0, svl.ids)],
            'line_ids': [
                (0, 0, {
                    'name': label,
                    'account_id': debit_account.id,
                    'product_id': product.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': label,
                    'account_id': credit_account.id,
                    'product_id': product.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        return move

    def _process_lines(self, lines, operation):
        """Run ``operation`` ('revalue' | 'regularize') over ``lines`` isolating
        each product in a savepoint, then surface a summary notification."""
        self.ensure_one()
        done = 0
        skipped = []
        for line in lines:
            try:
                with self.env.cr.savepoint():
                    if operation == 'revalue':
                        if line.revaluation_svl_id:
                            continue
                        svl = self._revalue_line(line)
                        line.revaluation_svl_id = svl.id
                    else:
                        if line.correction_move_id:
                            continue
                        move = self._regularize_line(line)
                        line.correction_move_id = move.id
                done += 1
            except UserError as err:
                skipped.append('%s: %s' % (line.product_id.display_name, err.args[0] if err.args else err))
        return done, skipped

    def _correction_notification(self, operation, done, skipped):
        if operation == 'revalue':
            title = _('Valuation recomputed')
            base = _('%s product(s) revalued.', done)
        else:
            title = _('Entries regularized')
            base = _('%s correction entry(ies) created in draft.', done)
        message = base
        if skipped:
            message += '\n' + _('Skipped:') + '\n' + '\n'.join('• %s' % s for s in skipped)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'warning' if skipped else 'success',
                'sticky': bool(skipped),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    # ------------------------------------------------------------------
    # Header actions
    # ------------------------------------------------------------------
    def action_recompute_valuation(self):
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda l: l.has_difference and not l.revaluation_svl_id)
        if not lines:
            raise UserError(_('There is nothing to revalue.'))
        done, skipped = self._process_lines(lines, 'revalue')
        return self._correction_notification('revalue', done, skipped)

    def action_regularize_entries(self):
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda l: l.revaluation_svl_id and not l.correction_move_id)
        if not lines:
            raise UserError(_('There are no revalued products pending an entry.'))
        done, skipped = self._process_lines(lines, 'regularize')
        return self._correction_notification('regularize', done, skipped)


class StockKardexCostAuditLine(models.Model):
    _name = 'stock.kardex.cost.audit.line'
    _description = 'Kardex Cost Audit Line'
    _order = 'has_difference desc, value_difference desc'

    audit_id = fields.Many2one(
        comodel_name='stock.kardex.cost.audit',
        string='Audit',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='audit_id.currency_id',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='audit_id.company_id',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True,
    )
    product_code = fields.Char(
        string='Reference',
        related='product_id.default_code',
    )
    qty_out = fields.Float(
        string='Qty Out',
        digits='Product Unit of Measure',
    )
    cogs_recorded = fields.Monetary(
        string='Recorded Output Cost',
        currency_field='currency_id',
        help='Cost of goods sold actually posted by Odoo for the outgoing '
             'layers within the period.',
    )
    cogs_wac = fields.Monetary(
        string='WAC Output Cost',
        currency_field='currency_id',
        help='Cost of goods sold recomputed with the chronological weighted '
             'average cost.',
    )
    cogs_difference = fields.Monetary(
        string='Output Difference',
        currency_field='currency_id',
        help='Recorded minus WAC. A non-zero value means the booked COGS does '
             'not match the valued kardex.',
    )
    qty_balance = fields.Float(
        string='Qty Balance',
        digits='Product Unit of Measure',
    )
    value_recorded = fields.Monetary(
        string='Recorded Balance Value',
        currency_field='currency_id',
        help='Inventory value at the end of the period as recorded by Odoo.',
    )
    value_wac = fields.Monetary(
        string='WAC Balance Value',
        currency_field='currency_id',
        help='Inventory value at the end of the period recomputed with the '
             'weighted average cost.',
    )
    value_difference = fields.Monetary(
        string='Balance Difference',
        currency_field='currency_id',
        help='Recorded minus WAC inventory value.',
    )
    has_difference = fields.Boolean(
        string='Has Difference',
    )
    revaluation_svl_id = fields.Many2one(
        comodel_name='stock.valuation.layer',
        string='Revaluation Layer',
        readonly=True,
    )
    correction_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Correction Entry',
        readonly=True,
    )
    correction_state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('revalued', 'Revalued'),
            ('regularized', 'Regularized'),
        ],
        string='Correction',
        compute='_compute_correction_state',
        store=True,
    )

    @api.depends('revaluation_svl_id', 'correction_move_id')
    def _compute_correction_state(self):
        for line in self:
            if line.correction_move_id:
                line.correction_state = 'regularized'
            elif line.revaluation_svl_id:
                line.correction_state = 'revalued'
            else:
                line.correction_state = 'pending'

    def action_line_recompute(self):
        self.ensure_one()
        if not self.has_difference:
            raise UserError(_('This product has no difference to correct.'))
        done, skipped = self.audit_id._process_lines(self, 'revalue')
        return self.audit_id._correction_notification('revalue', done, skipped)

    def action_line_regularize(self):
        self.ensure_one()
        done, skipped = self.audit_id._process_lines(self, 'regularize')
        return self.audit_id._correction_notification('regularize', done, skipped)

    def action_view_valuation_layers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Valuation Layers: %s', self.product_id.display_name),
            'res_model': 'stock.valuation.layer',
            'view_mode': 'list,form',
            'domain': [
                ('product_id', '=', self.product_id.id),
                ('company_id', '=', self.audit_id.company_id.id),
            ],
        }

    def action_open_correction_move(self):
        self.ensure_one()
        if not self.correction_move_id:
            raise UserError(_('No correction entry has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Correction Entry: %s', self.product_id.display_name),
            'res_model': 'account.move',
            'res_id': self.correction_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
