from odoo import models, _
from odoo.tools.misc import get_lang
from decimal import Decimal
import pytz
from datetime import datetime, time

ZERO = Decimal('0')
WAC_FETCH_SIZE = 2000


class StockKardexProductReportHandler(models.AbstractModel):
    _name = 'stock.kardex.product.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Stock Kardex Product Report Custom Handler'

    def _get_date_field_sql(self, options):
        if options.get('use_accounting_date'):
            return "COALESCE(svl.accounting_date, svl.create_date)"
        return "svl.create_date"

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        options['display_hierarchy_filter'] = False
        options['filter_category_ids'] = previous_options.get('filter_category_ids', [])
        options['filter_product_ids'] = previous_options.get('filter_product_ids', [])
        options['group_by_category'] = previous_options.get('group_by_category', False)
        options['use_accounting_date'] = self._resolve_use_accounting_date(report)

    def _resolve_use_accounting_date(self, report):
        if report.kardex_use_accounting_date or report.root_report_id.kardex_use_accounting_date:
            return True
        report_ref = report.get_external_id().get(report.id, '')
        return 'accounting' in report_ref.lower() or 'accounting' in (report.name or '').lower()

    def _custom_line_postprocessor(self, report, options, lines, warnings=None):
        if warnings:
            warnings.clear()
        return lines

    def _caret_options_initializer(self):
        return {
            'product.category': [
                {'name': _('Open Category'), 'action': 'open_record'},
                {'name': _('View Products'), 'action': 'open_products'},
                {'name': _('View Valuation Layers'), 'action': 'open_svl'},
                {'name': _('View Journal Entries'), 'action': 'open_journal_entries'},
                {'name': _('View Stock Moves'), 'action': 'open_stock_moves'},
                {'name': _('View Stock Move Lines'), 'action': 'open_stock_move_lines'},
            ],
            'product.product': [
                {'name': _('Open Product'), 'action': 'open_record'},
                {'name': _('View Valuation Layers'), 'action': 'open_svl'},
                {'name': _('View Journal Entries'), 'action': 'open_journal_entries'},
                {'name': _('View Stock Moves'), 'action': 'open_stock_moves'},
                {'name': _('View Stock Move Lines'), 'action': 'open_stock_move_lines'},
            ],
            'stock.lot': [
                {'name': _('Open Lot/Serial'), 'action': 'open_record'},
                {'name': _('View Valuation Layers'), 'action': 'open_svl'},
                {'name': _('View Journal Entries'), 'action': 'open_journal_entries'},
                {'name': _('View Stock Moves'), 'action': 'open_stock_moves'},
                {'name': _('View Stock Move Lines'), 'action': 'open_stock_move_lines'},
            ],
            'stock.valuation.layer': [
                {'name': _('Open Valuation Layer'), 'action': 'open_record'},
                {'name': _('Open Reference'), 'action': 'open_reference'},
                {'name': _('Open Journal Entry'), 'action': 'open_journal_entry'},
                {'name': _('Open Stock Move'), 'action': 'open_stock_move'},
                {'name': _('Open Stock Move Line'), 'action': 'open_stock_move_line'},
            ],
        }

    def _build_cache(self, options):
        cids = self._get_company_ids(options)
        company = self.env['res.company'].browse(cids[0]) if cids else self.env.company
        currency = company.currency_id
        tz_str = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        try:
            user_tz = pytz.timezone(tz_str)
        except pytz.exceptions.UnknownTimeZoneError:
            user_tz = pytz.UTC
        movement_types = {}
        if 'movement_type' in self.env['stock.move']._fields:
            movement_types = dict(self.env['stock.move']._fields['movement_type']._description_selection(self.env))
        return {
            'company_ids': tuple(cids),
            'currency': currency,
            'qty_digits': self.env['decimal.precision'].precision_get('Product Unit of Measure') or 2,
            'price_digits': self.env['decimal.precision'].precision_get('Product Price') or 2,
            'lang': self.env.user.lang or get_lang(self.env).code,
            'user_tz': user_tz,
            'movement_types': movement_types,
            'date_field': self._get_date_field_sql(options),
            'use_accounting_date': options.get('use_accounting_date', False),
        }

    def _get_company_ids(self, options):
        if options.get('multi_company'):
            return [c['id'] for c in options['multi_company'] if c.get('selected', True)]
        return self.env.companies.ids

    def _get_date_range_utc(self, options, cache):
        user_tz = cache['user_tz']
        df = options['date']['date_from']
        dt = options['date']['date_to']
        df_naive = datetime.strptime(df, '%Y-%m-%d') if isinstance(df, str) else datetime.combine(df, time.min)
        dt_naive = datetime.strptime(dt, '%Y-%m-%d') if isinstance(dt, str) else datetime.combine(dt, time.min)
        df_naive = df_naive.replace(hour=0, minute=0, second=0, microsecond=0)
        dt_naive = dt_naive.replace(hour=23, minute=59, second=59, microsecond=999999)
        return (
            user_tz.localize(df_naive).astimezone(pytz.UTC),
            user_tz.localize(dt_naive).astimezone(pytz.UTC)
        )

    def _get_date_range_orm(self, options):
        df = options['date']['date_from']
        dt = options['date']['date_to']
        df_naive = datetime.strptime(df, '%Y-%m-%d') if isinstance(df, str) else datetime.combine(df, time.min)
        dt_naive = datetime.strptime(dt, '%Y-%m-%d') if isinstance(dt, str) else datetime.combine(dt, time.min)
        return (
            df_naive.replace(hour=0, minute=0, second=0, microsecond=0),
            dt_naive.replace(hour=23, minute=59, second=59, microsecond=999999)
        )

    def _get_category_children(self, cat_id):
        cat = self.env['product.category'].with_context(active_test=False).browse(cat_id)
        if not cat.exists():
            return []
        return self.env['product.category'].with_context(active_test=False).search(
            [('parent_path', '=like', cat.parent_path + '%')]
        ).ids

    def _init_totals(self, options):
        groups = options.get('column_groups', {}) or {'default': {}}
        return {
            k: {
                'qty_in': 0.0, 'value_in': 0.0,
                'qty_out': 0.0, 'value_out': 0.0,
                'qty_balance': 0.0, 'value_balance': 0.0,
            }
            for k in groups
        }

    def _calc_unit_cost(self, standard_price, qty_balance, value_balance_calc, use_accounting_date=False):
        if use_accounting_date:
            if qty_balance:
                return value_balance_calc / qty_balance
            return 0.0
        if standard_price:
            return standard_price
        if qty_balance:
            return value_balance_calc / qty_balance
        return 0.0

    def _to_decimal(self, value):
        if value is None:
            return ZERO
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _wac_aggregate_by_key(self, query, params, n_key_cols):
        self.env.cr.execute(query, params)
        results = {}
        current_key = None
        qty_acum = ZERO
        value_acum = ZERO
        qty_in = ZERO
        value_in = ZERO
        qty_out = ZERO
        value_out = ZERO

        def flush(key):
            unit_cost = value_acum / qty_acum if qty_acum else ZERO
            results[key] = {
                'qty_in': qty_in,
                'value_in': value_in,
                'qty_out': qty_out,
                'value_out': value_out,
                'qty_balance': qty_acum,
                'value_balance': value_acum,
                'unit_cost_balance': unit_cost,
            }

        while True:
            rows = self.env.cr.fetchmany(WAC_FETCH_SIZE)
            if not rows:
                break
            for row in rows:
                key = row[0] if n_key_cols == 1 else tuple(row[:n_key_cols])
                qty = self._to_decimal(row[n_key_cols])
                unit_cost = self._to_decimal(row[n_key_cols + 1])
                value = self._to_decimal(row[n_key_cols + 2])
                in_period = bool(row[n_key_cols + 3])

                if current_key is not None and key != current_key:
                    flush(current_key)
                    qty_acum = ZERO
                    value_acum = ZERO
                    qty_in = ZERO
                    value_in = ZERO
                    qty_out = ZERO
                    value_out = ZERO
                current_key = key

                if qty > 0:
                    move_value = qty * unit_cost
                    qty_acum += qty
                    value_acum += move_value
                    if in_period:
                        qty_in += qty
                        value_in += move_value
                elif qty < 0:
                    abs_qty = -qty
                    if qty_acum > 0:
                        wac_prev = value_acum / qty_acum
                    else:
                        wac_prev = ZERO
                    move_value = abs_qty * wac_prev
                    qty_acum += qty
                    value_acum -= move_value
                    if qty_acum == ZERO:
                        value_acum = ZERO
                    if in_period:
                        qty_out += abs_qty
                        value_out += move_value
                else:
                    value_acum += value
                    if in_period:
                        if value > 0:
                            value_in += value
                        elif value < 0:
                            value_out += -value
        if current_key is not None:
            flush(current_key)
        return results

    def _wac_walk_layers(self, rows, columns, initial_qty=ZERO, initial_value=ZERO):
        qty_acum = initial_qty
        value_acum = initial_value
        for row in rows:
            data = dict(zip(columns, row))
            qty = self._to_decimal(data.get('quantity'))
            unit_cost = self._to_decimal(data.get('unit_cost'))
            value = self._to_decimal(data.get('value'))
            if qty > 0:
                move_unit_cost = unit_cost
                move_value = qty * unit_cost
                qty_acum += qty
                value_acum += move_value
                direction = 1
            elif qty < 0:
                abs_qty = -qty
                if qty_acum > 0:
                    move_unit_cost = value_acum / qty_acum
                else:
                    move_unit_cost = ZERO
                move_value = abs_qty * move_unit_cost
                qty_acum += qty
                value_acum -= move_value
                if qty_acum == ZERO:
                    value_acum = ZERO
                direction = -1
            else:
                move_unit_cost = unit_cost
                move_value = value
                value_acum += value
                direction = 0
            running_unit_cost = value_acum / qty_acum if qty_acum else ZERO
            data['_wac_unit_cost'] = move_unit_cost
            data['_wac_move_value'] = move_value
            data['_wac_direction'] = direction
            data['_wac_running_qty'] = qty_acum
            data['_wac_running_value'] = value_acum
            data['_wac_running_unit_cost'] = running_unit_cost
            yield data

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        if warnings:
            warnings.clear()
        cache = self._build_cache(options)
        totals = self._init_totals(options)
        if options.get('group_by_category'):
            main_lines = self._generate_category_lines(report, options, totals, cache)
        else:
            main_lines = self._generate_product_lines(report, options, totals, cache)
        total_line = self._generate_total_line(report, options, totals, cache)
        return [*[(0, line) for line in main_lines], (0, total_line)]

    def _generate_category_lines(self, report, options, totals, cache):
        use_accounting_date = cache.get('use_accounting_date', False)
        if use_accounting_date:
            return self._generate_category_lines_wac(report, options, totals, cache)
        return self._generate_category_lines_legacy(report, options, totals, cache)

    def _generate_category_lines_legacy(self, report, options, totals, cache):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        pid_filter, cat_filter, extra_params = self._build_product_filters(options)
        query = f"""
            WITH svl_data AS (
                SELECT
                    svl.product_id,
                    svl.quantity,
                    svl.value,
                    svl.unit_cost,
                    svl.standard_price,
                    {date_field} AS svl_date,
                    svl.id,
                    CASE WHEN svl.quantity != 0 THEN svl.quantity * svl.unit_cost ELSE svl.value END AS value_calc,
                    {date_field} >= %s AND {date_field} <= %s AS in_period
                FROM stock_valuation_layer svl
                WHERE {date_field} <= %s
                  AND svl.company_id IN %s
                  AND NOT EXISTS (
                      SELECT 1 FROM stock_move sm
                      WHERE sm.id = svl.stock_move_id AND sm.state != 'done'
                  )
            ),
            product_agg AS (
                SELECT
                    product_id,
                    SUM(quantity) FILTER (WHERE in_period AND quantity > 0) AS qty_in,
                    SUM(CASE WHEN quantity > 0 THEN value WHEN quantity = 0 AND value > 0 THEN value END) FILTER (WHERE in_period) AS value_in,
                    SUM(ABS(quantity)) FILTER (WHERE in_period AND quantity < 0) AS qty_out,
                    SUM(ABS(CASE WHEN quantity < 0 THEN value WHEN quantity = 0 AND value < 0 THEN value END)) FILTER (WHERE in_period) AS value_out,
                    SUM(quantity) AS qty_balance,
                    SUM(value) AS value_balance,
                    SUM(value_calc) AS value_balance_calc
                FROM svl_data
                GROUP BY product_id
                HAVING SUM(quantity) != 0 OR SUM(value) != 0 OR COUNT(*) FILTER (WHERE in_period) > 0
            )
            SELECT
                pt.categ_id,
                COALESCE(SUM(pa.qty_in), 0) AS qty_in,
                COALESCE(SUM(pa.value_in), 0) AS value_in,
                COALESCE(SUM(pa.qty_out), 0) AS qty_out,
                COALESCE(SUM(pa.value_out), 0) AS value_out,
                COALESCE(SUM(pa.qty_balance), 0) AS qty_balance,
                COALESCE(SUM(pa.value_balance), 0) AS value_balance,
                COALESCE(SUM(pa.value_balance_calc), 0) AS value_balance_calc
            FROM product_agg pa
            JOIN product_product pp ON pp.id = pa.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE pt.is_storable = true
            {pid_filter}
            {cat_filter}
            GROUP BY pt.categ_id
            ORDER BY pt.categ_id
        """
        params = [df, dt, dt, tuple(cids)] + extra_params
        self.env.cr.execute(query, params)
        rows = self.env.cr.fetchall()
        if not rows:
            return []
        columns = ['categ_id', 'qty_in', 'value_in', 'qty_out', 'value_out', 'qty_balance', 'value_balance', 'value_balance_calc']
        categ_ids = [r[0] for r in rows]
        categories = self.env['product.category'].browse(categ_ids)
        categ_names = {c.id: c.complete_name for c in categories}
        lines = []
        fk = next(iter(totals.keys()), None)
        for row in rows:
            row_dict = dict(zip(columns, row))
            categ_id = row_dict['categ_id']
            qty_balance = row_dict['qty_balance'] or 0
            value_balance = row_dict['value_balance'] or 0
            value_balance_calc = row_dict['value_balance_calc'] or 0
            unit_cost = self._calc_unit_cost(0, qty_balance, value_balance_calc, False)
            data = {
                fk: {
                    'qty_in': row_dict['qty_in'] or 0,
                    'value_in': row_dict['value_in'] or 0,
                    'qty_out': row_dict['qty_out'] or 0,
                    'value_out': row_dict['value_out'] or 0,
                    'qty_balance': qty_balance,
                    'value_balance': value_balance,
                    'unit_cost_balance': unit_cost,
                }
            }
            lid = report._get_generic_line_id('product.category', categ_id)
            lines.append({
                'id': lid,
                'name': categ_names.get(categ_id, ''),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': 1,
                'unfoldable': True,
                'unfolded': lid in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_category',
                'caret_options': 'product.category',
            })
            totals[fk]['qty_in'] += data[fk]['qty_in']
            totals[fk]['value_in'] += data[fk]['value_in']
            totals[fk]['qty_out'] += data[fk]['qty_out']
            totals[fk]['value_out'] += data[fk]['value_out']
            totals[fk]['qty_balance'] += data[fk]['qty_balance']
            totals[fk]['value_balance'] += data[fk]['value_balance']
        return lines

    def _generate_category_lines_wac(self, report, options, totals, cache):
        per_product = self._collect_product_wac(options, cache)
        if not per_product:
            return []
        product_ids = list(per_product.keys())
        product_to_categ = dict(self.env['product.product'].browse(product_ids).mapped(lambda p: (p.id, p.categ_id.id)))
        per_categ = {}
        for pid, agg in per_product.items():
            categ_id = product_to_categ.get(pid)
            if not categ_id:
                continue
            slot = per_categ.setdefault(categ_id, {
                'qty_in': ZERO, 'value_in': ZERO,
                'qty_out': ZERO, 'value_out': ZERO,
                'qty_balance': ZERO, 'value_balance': ZERO,
            })
            slot['qty_in'] += agg['qty_in']
            slot['value_in'] += agg['value_in']
            slot['qty_out'] += agg['qty_out']
            slot['value_out'] += agg['value_out']
            slot['qty_balance'] += agg['qty_balance']
            slot['value_balance'] += agg['value_balance']
        if not per_categ:
            return []
        categ_ids = sorted(per_categ.keys())
        categories = self.env['product.category'].browse(categ_ids)
        categ_names = {c.id: c.complete_name for c in categories}
        lines = []
        fk = next(iter(totals.keys()), None)
        for categ_id in categ_ids:
            slot = per_categ[categ_id]
            qty_balance = slot['qty_balance']
            value_balance = slot['value_balance']
            unit_cost = value_balance / qty_balance if qty_balance else ZERO
            data = {
                fk: {
                    'qty_in': float(slot['qty_in']),
                    'value_in': float(slot['value_in']),
                    'qty_out': float(slot['qty_out']),
                    'value_out': float(slot['value_out']),
                    'qty_balance': float(qty_balance),
                    'value_balance': float(value_balance),
                    'unit_cost_balance': float(unit_cost),
                }
            }
            lid = report._get_generic_line_id('product.category', categ_id)
            lines.append({
                'id': lid,
                'name': categ_names.get(categ_id, ''),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': 1,
                'unfoldable': True,
                'unfolded': lid in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_category',
                'caret_options': 'product.category',
            })
            totals[fk]['qty_in'] += data[fk]['qty_in']
            totals[fk]['value_in'] += data[fk]['value_in']
            totals[fk]['qty_out'] += data[fk]['qty_out']
            totals[fk]['value_out'] += data[fk]['value_out']
            totals[fk]['qty_balance'] += data[fk]['qty_balance']
            totals[fk]['value_balance'] += data[fk]['value_balance']
        return lines

    def _collect_product_wac(self, options, cache, parent_categ_id=None):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        pid_filter, cat_filter, extra_params = self._build_product_filters(options)
        categ_filter = ""
        categ_params = []
        if parent_categ_id:
            categ_filter = "AND pt.categ_id = %s"
            categ_params = [parent_categ_id]
        query = f"""
            SELECT
                svl.product_id,
                svl.quantity,
                svl.unit_cost,
                svl.value,
                ({date_field} >= %s AND {date_field} <= %s) AS in_period
            FROM stock_valuation_layer svl
            JOIN product_product pp ON pp.id = svl.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE {date_field} <= %s
              AND svl.company_id IN %s
              AND pt.is_storable = true
              AND NOT EXISTS (
                  SELECT 1 FROM stock_move sm
                  WHERE sm.id = svl.stock_move_id AND sm.state != 'done'
              )
              AND COALESCE(svl.kardex_cost_correction, false) = false
              {pid_filter}
              {cat_filter}
              {categ_filter}
            ORDER BY svl.product_id, {date_field}, svl.id
        """
        params = [df, dt, dt, tuple(cids)] + extra_params + categ_params
        return self._wac_aggregate_by_key(query, params, n_key_cols=1)

    def _generate_product_lines(self, report, options, totals, cache, parent_categ_id=None, parent_line_id=None):
        use_accounting_date = cache.get('use_accounting_date', False)
        if use_accounting_date:
            return self._generate_product_lines_wac(report, options, totals, cache, parent_categ_id, parent_line_id)
        return self._generate_product_lines_legacy(report, options, totals, cache, parent_categ_id, parent_line_id)

    def _generate_product_lines_legacy(self, report, options, totals, cache, parent_categ_id=None, parent_line_id=None):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        use_accounting_date = cache.get('use_accounting_date', False)
        pid_filter, cat_filter, extra_params = self._build_product_filters(options)
        categ_filter = ""
        categ_params = []
        if parent_categ_id:
            categ_filter = "AND pt.categ_id = %s"
            categ_params = [parent_categ_id]
        query = f"""
            WITH svl_data AS (
                SELECT 
                    svl.product_id,
                    svl.quantity,
                    svl.value,
                    svl.unit_cost,
                    svl.standard_price,
                    {date_field} AS svl_date,
                    svl.id,
                    CASE WHEN svl.quantity != 0 THEN svl.quantity * svl.unit_cost ELSE svl.value END AS value_calc,
                    {date_field} >= %s AND {date_field} <= %s AS in_period
                FROM stock_valuation_layer svl
                WHERE {date_field} <= %s
                  AND svl.company_id IN %s
                  AND NOT EXISTS (
                      SELECT 1 FROM stock_move sm 
                      WHERE sm.id = svl.stock_move_id AND sm.state != 'done'
                  )
            ),
            product_agg AS (
                SELECT 
                    product_id,
                    SUM(quantity) FILTER (WHERE in_period AND quantity > 0) AS qty_in,
                    SUM(CASE WHEN quantity > 0 THEN value WHEN quantity = 0 AND value > 0 THEN value END) FILTER (WHERE in_period) AS value_in,
                    SUM(ABS(quantity)) FILTER (WHERE in_period AND quantity < 0) AS qty_out,
                    SUM(ABS(CASE WHEN quantity < 0 THEN value WHEN quantity = 0 AND value < 0 THEN value END)) FILTER (WHERE in_period) AS value_out,
                    SUM(quantity) AS qty_balance,
                    SUM(value) AS value_balance,
                    SUM(value_calc) AS value_balance_calc,
                    (ARRAY_AGG(standard_price ORDER BY svl_date DESC, id DESC))[1] AS last_standard_price
                FROM svl_data
                GROUP BY product_id
                HAVING SUM(quantity) != 0 OR SUM(value) != 0 OR COUNT(*) FILTER (WHERE in_period) > 0
            )
            SELECT 
                pp.id,
                COALESCE(pa.qty_in, 0) AS qty_in,
                COALESCE(pa.value_in, 0) AS value_in,
                COALESCE(pa.qty_out, 0) AS qty_out,
                COALESCE(pa.value_out, 0) AS value_out,
                COALESCE(pa.qty_balance, 0) AS qty_balance,
                COALESCE(pa.value_balance, 0) AS value_balance,
                COALESCE(pa.value_balance_calc, 0) AS value_balance_calc,
                COALESCE(pa.last_standard_price, 0) AS last_standard_price,
                COALESCE(pt.lot_valuated, false) AS lot_valuated
            FROM product_agg pa
            JOIN product_product pp ON pp.id = pa.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE pt.is_storable = true
            {pid_filter}
            {cat_filter}
            {categ_filter}
            ORDER BY pp.id
        """
        params = [df, dt, dt, tuple(cids)] + extra_params + categ_params
        self.env.cr.execute(query, params)
        rows = self.env.cr.fetchall()
        if not rows:
            return []
        columns = ['id', 'qty_in', 'value_in', 'qty_out', 'value_out', 'qty_balance', 'value_balance', 'value_balance_calc', 'last_standard_price', 'lot_valuated']
        product_ids = [r[0] for r in rows]
        products = self.env['product.product'].browse(product_ids)
        product_names = {p.id: p.display_name for p in products}
        lines = []
        fk = next(iter(totals.keys()), None)
        level = 2 if parent_categ_id else 1
        for row in rows:
            row_dict = dict(zip(columns, row))
            pid = row_dict['id']
            qty_balance = row_dict['qty_balance'] or 0
            value_balance = row_dict['value_balance'] or 0
            value_balance_calc = row_dict['value_balance_calc'] or 0
            lot_valuated = row_dict['lot_valuated']
            last_standard_price = row_dict['last_standard_price'] or 0
            if use_accounting_date:
                unit_cost = self._calc_unit_cost(0, qty_balance, value_balance_calc, True)
            elif lot_valuated:
                unit_cost = value_balance_calc / qty_balance if qty_balance else 0
            else:
                unit_cost = self._calc_unit_cost(last_standard_price, qty_balance, value_balance_calc, False)
            data = {
                fk: {
                    'qty_in': row_dict['qty_in'] or 0,
                    'value_in': row_dict['value_in'] or 0,
                    'qty_out': row_dict['qty_out'] or 0,
                    'value_out': row_dict['value_out'] or 0,
                    'qty_balance': qty_balance,
                    'value_balance': value_balance,
                    'unit_cost_balance': unit_cost,
                }
            }
            if parent_line_id:
                lid = report._get_generic_line_id('product.product', pid, parent_line_id=parent_line_id)
            else:
                lid = report._get_generic_line_id('product.product', pid)
            line_data = {
                'id': lid,
                'name': product_names.get(pid, ''),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': level,
                'unfoldable': True,
                'unfolded': lid in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_product',
                'caret_options': 'product.product',
            }
            if parent_line_id:
                line_data['parent_id'] = parent_line_id
            lines.append(line_data)
            if not parent_categ_id:
                totals[fk]['qty_in'] += data[fk]['qty_in']
                totals[fk]['value_in'] += data[fk]['value_in']
                totals[fk]['qty_out'] += data[fk]['qty_out']
                totals[fk]['value_out'] += data[fk]['value_out']
                totals[fk]['qty_balance'] += data[fk]['qty_balance']
                totals[fk]['value_balance'] += data[fk]['value_balance']
        return lines

    def _generate_product_lines_wac(self, report, options, totals, cache, parent_categ_id=None, parent_line_id=None):
        per_product = self._collect_product_wac(options, cache, parent_categ_id=parent_categ_id)
        if not per_product:
            return []
        product_ids = sorted(per_product.keys())
        products = self.env['product.product'].browse(product_ids)
        product_names = {p.id: p.display_name for p in products}
        lines = []
        fk = next(iter(totals.keys()), None)
        level = 2 if parent_categ_id else 1
        for pid in product_ids:
            agg = per_product[pid]
            qty_balance = agg['qty_balance']
            value_balance = agg['value_balance']
            unit_cost = value_balance / qty_balance if qty_balance else ZERO
            data = {
                fk: {
                    'qty_in': float(agg['qty_in']),
                    'value_in': float(agg['value_in']),
                    'qty_out': float(agg['qty_out']),
                    'value_out': float(agg['value_out']),
                    'qty_balance': float(qty_balance),
                    'value_balance': float(value_balance),
                    'unit_cost_balance': float(unit_cost),
                }
            }
            if parent_line_id:
                lid = report._get_generic_line_id('product.product', pid, parent_line_id=parent_line_id)
            else:
                lid = report._get_generic_line_id('product.product', pid)
            line_data = {
                'id': lid,
                'name': product_names.get(pid, ''),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': level,
                'unfoldable': True,
                'unfolded': lid in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_product',
                'caret_options': 'product.product',
            }
            if parent_line_id:
                line_data['parent_id'] = parent_line_id
            lines.append(line_data)
            if not parent_categ_id:
                totals[fk]['qty_in'] += data[fk]['qty_in']
                totals[fk]['value_in'] += data[fk]['value_in']
                totals[fk]['qty_out'] += data[fk]['qty_out']
                totals[fk]['value_out'] += data[fk]['value_out']
                totals[fk]['qty_balance'] += data[fk]['qty_balance']
                totals[fk]['value_balance'] += data[fk]['value_balance']
        return lines

    def _build_product_filters(self, options):
        pid_filter = ""
        cat_filter = ""
        extra_params = []
        pids = options.get('filter_product_ids', [])
        catids = options.get('filter_category_ids', [])
        if pids:
            pid_filter = "AND pp.id IN %s"
            extra_params.append(tuple(pids))
        if catids:
            all_cats = []
            for c in catids:
                all_cats.extend(self._get_category_children(c))
            if all_cats:
                cat_filter = "AND pt.categ_id IN %s"
                extra_params.append(tuple(all_cats))
        return pid_filter, cat_filter, extra_params

    def _generate_total_line(self, report, options, totals, cache):
        return {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('Total'),
            'level': 1,
            'columns': self._build_columns(report, options, totals, cache, False),
        }

    def _report_expand_unfoldable_line_category(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        report = self.env['account.report'].browse(options['report_id'])
        categ_id = self._extract_model_id(report, line_dict_id, 'product.category')
        if not categ_id:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        cache = self._build_cache(options)
        totals = self._init_totals(options)
        lines = self._generate_product_lines(report, options, totals, cache, parent_categ_id=categ_id, parent_line_id=line_dict_id)
        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}

    def _report_expand_unfoldable_line_product(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        report = self.env['account.report'].browse(options['report_id'])
        pid = self._extract_model_id(report, line_dict_id, 'product.product')
        if not pid:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        cache = self._build_cache(options)
        self.env.cr.execute("""
            SELECT COALESCE(pt.lot_valuated, false)
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE pp.id = %s
        """, [pid])
        row = self.env.cr.fetchone()
        lot_valuated = row[0] if row else False
        if lot_valuated:
            lines = self._expand_lot_lines(report, options, line_dict_id, pid, cache)
            return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}
        return self._expand_svl_lines(report, options, line_dict_id, pid, None, offset, cache, progress=progress)

    def _report_expand_unfoldable_line_lot(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        report = self.env['account.report'].browse(options['report_id'])
        parsed = report._parse_line_id(line_dict_id)
        pid = lot_id = None
        no_lot = False
        for markup, model, rid in parsed:
            if model == 'product.product':
                pid = rid
            elif model == 'stock.lot':
                lot_id = rid
            elif markup == 'no_lot':
                no_lot = True
        if not pid:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        cache = self._build_cache(options)
        return self._expand_svl_lines(report, options, line_dict_id, pid, None if no_lot else lot_id, offset, cache, progress=progress)

    def _expand_lot_lines(self, report, options, parent_id, pid, cache):
        use_accounting_date = cache.get('use_accounting_date', False)
        if use_accounting_date:
            return self._expand_lot_lines_wac(report, options, parent_id, pid, cache)
        return self._expand_lot_lines_legacy(report, options, parent_id, pid, cache)

    def _expand_lot_lines_legacy(self, report, options, parent_id, pid, cache):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        use_accounting_date = cache.get('use_accounting_date', False)
        query = f"""
            WITH svl_data AS (
                SELECT
                    svl.lot_id,
                    svl.quantity,
                    svl.value,
                    svl.unit_cost,
                    svl.standard_price,
                    {date_field} AS svl_date,
                    svl.id,
                    CASE WHEN svl.quantity != 0 THEN svl.quantity * svl.unit_cost ELSE svl.value END AS value_calc,
                    {date_field} >= %s AND {date_field} <= %s AS in_period
                FROM stock_valuation_layer svl
                WHERE svl.product_id = %s
                  AND {date_field} <= %s
                  AND svl.company_id IN %s
                  AND NOT EXISTS (
                      SELECT 1 FROM stock_move sm 
                      WHERE sm.id = svl.stock_move_id AND sm.state != 'done'
                  )
            ),
            lot_agg AS (
                SELECT 
                    lot_id,
                    SUM(quantity) FILTER (WHERE in_period AND quantity > 0) AS qty_in,
                    SUM(CASE WHEN quantity > 0 THEN value WHEN quantity = 0 AND value > 0 THEN value END) FILTER (WHERE in_period) AS value_in,
                    SUM(ABS(quantity)) FILTER (WHERE in_period AND quantity < 0) AS qty_out,
                    SUM(ABS(CASE WHEN quantity < 0 THEN value WHEN quantity = 0 AND value < 0 THEN value END)) FILTER (WHERE in_period) AS value_out,
                    SUM(quantity) AS qty_balance,
                    SUM(value) AS value_balance,
                    SUM(value_calc) AS value_balance_calc,
                    (ARRAY_AGG(standard_price ORDER BY svl_date DESC, id DESC))[1] AS last_standard_price
                FROM svl_data
                GROUP BY lot_id
                HAVING SUM(quantity) != 0 OR SUM(value) != 0 OR COUNT(*) FILTER (WHERE in_period) > 0
            )
            SELECT 
                la.lot_id,
                lot.name AS lot_name,
                COALESCE(la.qty_in, 0) AS qty_in,
                COALESCE(la.value_in, 0) AS value_in,
                COALESCE(la.qty_out, 0) AS qty_out,
                COALESCE(la.value_out, 0) AS value_out,
                COALESCE(la.qty_balance, 0) AS qty_balance,
                COALESCE(la.value_balance, 0) AS value_balance,
                COALESCE(la.value_balance_calc, 0) AS value_balance_calc,
                COALESCE(la.last_standard_price, 0) AS last_standard_price
            FROM lot_agg la
            LEFT JOIN stock_lot lot ON lot.id = la.lot_id
            ORDER BY lot.name NULLS LAST
        """
        self.env.cr.execute(query, [df, dt, pid, dt, tuple(cids)])
        rows = self.env.cr.fetchall()
        if not rows:
            return []
        columns = ['lot_id', 'lot_name', 'qty_in', 'value_in', 'qty_out', 'value_out', 'qty_balance', 'value_balance', 'value_balance_calc', 'last_standard_price']
        lines = []
        fk = next(iter(self._init_totals(options).keys()), None)
        for row in rows:
            row_dict = dict(zip(columns, row))
            lid = row_dict['lot_id']
            qty_balance = row_dict['qty_balance'] or 0
            value_balance = row_dict['value_balance'] or 0
            value_balance_calc = row_dict['value_balance_calc'] or 0
            last_standard_price = row_dict['last_standard_price'] or 0
            unit_cost = self._calc_unit_cost(last_standard_price, qty_balance, value_balance_calc, use_accounting_date)
            data = {
                fk: {
                    'qty_in': row_dict['qty_in'] or 0,
                    'value_in': row_dict['value_in'] or 0,
                    'qty_out': row_dict['qty_out'] or 0,
                    'value_out': row_dict['value_out'] or 0,
                    'qty_balance': qty_balance,
                    'value_balance': value_balance,
                    'unit_cost_balance': unit_cost,
                }
            }
            if lid:
                line_id = report._get_generic_line_id('stock.lot', lid, parent_line_id=parent_id)
            else:
                line_id = report._get_generic_line_id(None, None, parent_line_id=parent_id, markup='no_lot')
            lines.append({
                'id': line_id,
                'parent_id': parent_id,
                'name': row_dict['lot_name'] or _('No Lot'),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': 3,
                'unfoldable': True,
                'unfolded': line_id in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_lot',
                'caret_options': 'stock.lot' if lid else None,
            })
        return lines

    def _expand_lot_lines_wac(self, report, options, parent_id, pid, cache):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        query = f"""
            SELECT
                svl.lot_id,
                svl.quantity,
                svl.unit_cost,
                svl.value,
                ({date_field} >= %s AND {date_field} <= %s) AS in_period
            FROM stock_valuation_layer svl
            WHERE svl.product_id = %s
              AND {date_field} <= %s
              AND svl.company_id IN %s
              AND NOT EXISTS (
                  SELECT 1 FROM stock_move sm
                  WHERE sm.id = svl.stock_move_id AND sm.state != 'done'
              )
              AND COALESCE(svl.kardex_cost_correction, false) = false
            ORDER BY svl.lot_id NULLS LAST, {date_field}, svl.id
        """
        params = [df, dt, pid, dt, tuple(cids)]
        per_lot = self._wac_aggregate_by_key(query, params, n_key_cols=1)
        if not per_lot:
            return []
        lot_ids = [lid for lid in per_lot.keys() if lid]
        lot_names = {}
        if lot_ids:
            for lot in self.env['stock.lot'].browse(lot_ids):
                lot_names[lot.id] = lot.name
        ordered_keys = sorted(per_lot.keys(), key=lambda k: (k is None, lot_names.get(k, '') if k else ''))
        lines = []
        fk = next(iter(self._init_totals(options).keys()), None)
        for lid_key in ordered_keys:
            agg = per_lot[lid_key]
            qty_balance = agg['qty_balance']
            value_balance = agg['value_balance']
            unit_cost = value_balance / qty_balance if qty_balance else ZERO
            data = {
                fk: {
                    'qty_in': float(agg['qty_in']),
                    'value_in': float(agg['value_in']),
                    'qty_out': float(agg['qty_out']),
                    'value_out': float(agg['value_out']),
                    'qty_balance': float(qty_balance),
                    'value_balance': float(value_balance),
                    'unit_cost_balance': float(unit_cost),
                }
            }
            if lid_key:
                line_id = report._get_generic_line_id('stock.lot', lid_key, parent_line_id=parent_id)
                name = lot_names.get(lid_key) or _('No Lot')
            else:
                line_id = report._get_generic_line_id(None, None, parent_line_id=parent_id, markup='no_lot')
                name = _('No Lot')
            lines.append({
                'id': line_id,
                'parent_id': parent_id,
                'name': name,
                'columns': self._build_columns(report, options, data, cache, True),
                'level': 3,
                'unfoldable': True,
                'unfolded': line_id in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_lot',
                'caret_options': 'stock.lot' if lid_key else None,
            })
        return lines

    def _expand_svl_lines(self, report, options, parent_id, pid, lot_id, offset, cache, progress=None):
        use_accounting_date = cache.get('use_accounting_date', False)
        if use_accounting_date:
            return self._expand_svl_lines_wac(report, options, parent_id, pid, lot_id, offset, cache, progress=progress)
        return self._expand_svl_lines_legacy(report, options, parent_id, pid, lot_id, offset, cache)

    def _expand_svl_lines_legacy(self, report, options, parent_id, pid, lot_id, offset, cache):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        lang = cache['lang']
        date_field = cache['date_field']
        use_accounting_date = cache.get('use_accounting_date', False)
        lot_filter = "AND svl.lot_id = %s" if lot_id else "AND svl.lot_id IS NULL" if lot_id is not None else ""
        lot_params = [lot_id] if lot_id else []
        base_params = [pid, df, tuple(cids)] + lot_params
        self.env.cr.execute(f"""
            SELECT
                COALESCE(SUM(svl.quantity), 0),
                COALESCE(SUM(svl.value), 0),
                COALESCE(SUM(CASE WHEN svl.quantity != 0 THEN svl.quantity * svl.unit_cost ELSE svl.value END), 0),
                (ARRAY_AGG(svl.standard_price ORDER BY {date_field} DESC, svl.id DESC) FILTER (WHERE svl.standard_price IS NOT NULL))[1]
            FROM stock_valuation_layer svl
            WHERE svl.product_id = %s
              AND {date_field} < %s
              AND svl.company_id IN %s
              AND NOT EXISTS (SELECT 1 FROM stock_move sm WHERE sm.id = svl.stock_move_id AND sm.state != 'done')
              {lot_filter}
        """, base_params)
        ib_row = self.env.cr.fetchone()
        initial_qty = ib_row[0] or 0
        initial_value = ib_row[1] or 0
        initial_value_calc = ib_row[2] or 0
        initial_standard_price = ib_row[3] or 0
        initial_unit_cost = self._calc_unit_cost(initial_standard_price, initial_qty, initial_value_calc, use_accounting_date)
        lines = []
        if offset == 0:
            lines.append({
                'id': report._get_generic_line_id(None, None, parent_line_id=parent_id, markup='initial_balance'),
                'parent_id': parent_id,
                'name': _('Initial Balance'),
                'columns': self._build_balance_columns(report, options, {
                    'qty_balance': initial_qty,
                    'value_balance': initial_value,
                    'unit_cost': initial_unit_cost,
                }, cache),
                'level': 3,
            })
        limit = report.load_more_limit if report.load_more_limit and options.get('export_mode') != 'print' else None
        limit_clause = f"LIMIT {limit + 1}" if limit else ""
        offset_clause = f"OFFSET {offset}" if offset else ""
        query = f"""
            SELECT 
                svl.id,
                {date_field} AS svl_date,
                svl.description,
                svl.quantity,
                svl.unit_cost,
                svl.value,
                svl.standard_price,
                svl.stock_move_id,
                sm.reference,
                sm.origin,
                sm.movement_type,
                picking.name AS picking_name,
                {initial_qty} + SUM(svl.quantity) OVER w AS running_qty,
                {initial_value} + SUM(svl.value) OVER w AS running_value,
                {initial_value_calc} + SUM(CASE WHEN svl.quantity != 0 THEN svl.quantity * svl.unit_cost ELSE svl.value END) OVER w AS running_value_calc
            FROM stock_valuation_layer svl
            LEFT JOIN stock_move sm ON sm.id = svl.stock_move_id
            LEFT JOIN stock_picking picking ON picking.id = sm.picking_id
            WHERE svl.product_id = %s 
              AND {date_field} >= %s AND {date_field} <= %s
              AND svl.company_id IN %s
              AND NOT EXISTS (SELECT 1 FROM stock_move sm2 WHERE sm2.id = svl.stock_move_id AND sm2.state != 'done')
              {lot_filter}
            WINDOW w AS (ORDER BY {date_field}, svl.id)
            ORDER BY {date_field}, svl.id
            {limit_clause} {offset_clause}
        """
        svl_params = [pid, df, dt, tuple(cids)] + lot_params
        self.env.cr.execute(query, svl_params)
        layers = self.env.cr.fetchall()
        has_more = False
        if limit and len(layers) > limit:
            has_more = True
            layers = layers[:limit]
        if not layers:
            return {
                'lines': lines,
                'offset_increment': 0,
                'has_more': False,
                'progress': {},
            }
        self.env.cr.execute(f"""
            SELECT COALESCE(uom.name->>%s, uom.name->>'en_US', uom.name::text)
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            JOIN uom_uom uom ON uom.id = pt.uom_id
            WHERE pp.id = %s
        """, [lang, pid])
        uom_row = self.env.cr.fetchone()
        uom_name = uom_row[0] if uom_row else ''
        columns = ['id', 'svl_date', 'description', 'quantity', 'unit_cost', 'value', 'standard_price',
                   'stock_move_id', 'reference', 'origin', 'movement_type', 'picking_name',
                   'running_qty', 'running_value', 'running_value_calc']
        movement_types = cache['movement_types']
        user_tz = cache['user_tz']
        qd = cache['qty_digits']
        pd = cache['price_digits']
        cur = cache['currency']
        for layer_tuple in layers:
            layer = dict(zip(columns, layer_tuple))
            running_qty = layer['running_qty'] or 0
            running_value = layer['running_value'] or 0
            running_value_calc = layer['running_value_calc'] or 0
            standard_price = layer['standard_price'] or 0
            unit_cost = self._calc_unit_cost(standard_price, running_qty, running_value_calc, use_accounting_date)
            balance = {
                'qty_balance': running_qty,
                'value_balance': running_value,
                'unit_cost': unit_cost,
            }
            name = layer.get('picking_name') or layer.get('reference') or layer.get('description') or ''
            lines.append({
                'id': report._get_generic_line_id('stock.valuation.layer', layer['id'], parent_line_id=parent_id),
                'parent_id': parent_id,
                'name': name,
                'columns': self._build_layer_columns_fast(report, options, layer, balance, user_tz, movement_types, qd, pd, cur, uom_name, use_accounting_date),
                'level': 3,
                'caret_options': 'stock.valuation.layer',
            })
        return {
            'lines': lines,
            'offset_increment': len(layers),
            'has_more': has_more,
            'progress': {},
        }

    def _compute_svl_initial_balance(self, pid, df, cids, date_field, lot_filter, lot_params):
        ib_query = f"""
            SELECT
                svl.quantity,
                svl.unit_cost,
                svl.value
            FROM stock_valuation_layer svl
            WHERE svl.product_id = %s
              AND {date_field} < %s
              AND svl.company_id IN %s
              AND NOT EXISTS (SELECT 1 FROM stock_move sm WHERE sm.id = svl.stock_move_id AND sm.state != 'done')
              AND COALESCE(svl.kardex_cost_correction, false) = false
              {lot_filter}
            ORDER BY {date_field}, svl.id
        """
        self.env.cr.execute(ib_query, [pid, df, tuple(cids)] + lot_params)
        initial_qty = ZERO
        initial_value = ZERO
        while True:
            rows = self.env.cr.fetchmany(WAC_FETCH_SIZE)
            if not rows:
                break
            for row in rows:
                qty = self._to_decimal(row[0])
                unit_cost = self._to_decimal(row[1])
                value = self._to_decimal(row[2])
                if qty > 0:
                    initial_qty += qty
                    initial_value += qty * unit_cost
                elif qty < 0:
                    abs_qty = -qty
                    wac_prev = initial_value / initial_qty if initial_qty > 0 else ZERO
                    initial_qty += qty
                    initial_value -= abs_qty * wac_prev
                    if initial_qty == ZERO:
                        initial_value = ZERO
                else:
                    initial_value += value
        return initial_qty, initial_value

    def _expand_svl_lines_wac(self, report, options, parent_id, pid, lot_id, offset, cache, progress=None):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        lang = cache['lang']
        date_field = cache['date_field']
        lot_filter = "AND svl.lot_id = %s" if lot_id else "AND svl.lot_id IS NULL" if lot_id is not None else ""
        lot_params = [lot_id] if lot_id else []
        limit = report.load_more_limit if report.load_more_limit and options.get('export_mode') != 'print' else None

        progress = progress or {}
        has_seed = bool(offset) and 'wac_qty' in progress
        if has_seed:
            initial_qty = self._to_decimal(progress.get('initial_qty'))
            initial_value = self._to_decimal(progress.get('initial_value'))
            qty_acum = self._to_decimal(progress.get('wac_qty'))
            value_acum = self._to_decimal(progress.get('wac_value'))
        else:
            initial_qty, initial_value = self._compute_svl_initial_balance(
                pid, df, cids, date_field, lot_filter, lot_params)
            qty_acum = initial_qty
            value_acum = initial_value

        lines = []
        if offset == 0:
            initial_unit_cost = initial_value / initial_qty if initial_qty else ZERO
            lines.append({
                'id': report._get_generic_line_id(None, None, parent_line_id=parent_id, markup='initial_balance'),
                'parent_id': parent_id,
                'name': _('Initial Balance'),
                'columns': self._build_balance_columns(report, options, {
                    'qty_balance': float(initial_qty),
                    'value_balance': float(initial_value),
                    'unit_cost': float(initial_unit_cost),
                }, cache),
                'level': 3,
            })

        self.env.cr.execute("""
            SELECT COALESCE(uom.name->>%s, uom.name->>'en_US', uom.name::text)
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            JOIN uom_uom uom ON uom.id = pt.uom_id
            WHERE pp.id = %s
        """, [lang, pid])
        uom_row = self.env.cr.fetchone()
        uom_name = uom_row[0] if uom_row else ''
        movement_types = cache['movement_types']
        user_tz = cache['user_tz']
        qd = cache['qty_digits']
        pd = cache['price_digits']
        cur = cache['currency']

        if limit is not None:
            if has_seed:
                window_clause = f"OFFSET {offset} LIMIT {limit + 1}"
                start_index = offset
            else:
                window_clause = f"LIMIT {offset + limit + 1}"
                start_index = 0
        else:
            window_clause = ""
            start_index = 0

        period_query = f"""
            SELECT
                svl.id,
                {date_field} AS svl_date,
                svl.description,
                svl.quantity,
                svl.unit_cost,
                svl.value,
                svl.standard_price,
                svl.stock_move_id,
                sm.reference,
                sm.origin,
                sm.movement_type,
                picking.name AS picking_name
            FROM stock_valuation_layer svl
            LEFT JOIN stock_move sm ON sm.id = svl.stock_move_id
            LEFT JOIN stock_picking picking ON picking.id = sm.picking_id
            WHERE svl.product_id = %s
              AND {date_field} >= %s AND {date_field} <= %s
              AND svl.company_id IN %s
              AND NOT EXISTS (SELECT 1 FROM stock_move sm2 WHERE sm2.id = svl.stock_move_id AND sm2.state != 'done')
              AND COALESCE(svl.kardex_cost_correction, false) = false
              {lot_filter}
            ORDER BY {date_field}, svl.id
            {window_clause}
        """
        period_params = [pid, df, dt, tuple(cids)] + lot_params
        self.env.cr.execute(period_query, period_params)
        columns = ['id', 'svl_date', 'description', 'quantity', 'unit_cost', 'value', 'standard_price',
                   'stock_move_id', 'reference', 'origin', 'movement_type', 'picking_name']

        page = []
        page_qty_acum = qty_acum
        page_value_acum = value_acum
        result_index = start_index
        page_end = (offset + limit) if limit is not None else None
        has_more = False
        done = False
        while not done:
            rows = self.env.cr.fetchmany(WAC_FETCH_SIZE)
            if not rows:
                break
            for row in rows:
                if page_end is not None and result_index >= page_end:
                    has_more = True
                    done = True
                    break
                layer = dict(zip(columns, row))
                qty = self._to_decimal(layer.get('quantity'))
                unit_cost = self._to_decimal(layer.get('unit_cost'))
                value = self._to_decimal(layer.get('value'))
                if qty > 0:
                    move_unit_cost = unit_cost
                    move_value = qty * unit_cost
                    qty_acum += qty
                    value_acum += move_value
                elif qty < 0:
                    abs_qty = -qty
                    move_unit_cost = value_acum / qty_acum if qty_acum > 0 else ZERO
                    move_value = abs_qty * move_unit_cost
                    qty_acum += qty
                    value_acum -= move_value
                    if qty_acum == ZERO:
                        value_acum = ZERO
                else:
                    move_unit_cost = unit_cost
                    move_value = value
                    value_acum += value
                if result_index >= offset:
                    running_unit_cost = value_acum / qty_acum if qty_acum else ZERO
                    layer['_wac_unit_cost'] = float(move_unit_cost)
                    layer['_wac_move_value'] = float(move_value)
                    layer['_wac_running_qty'] = float(qty_acum)
                    layer['_wac_running_value'] = float(value_acum)
                    layer['_wac_running_unit_cost'] = float(running_unit_cost)
                    page.append(layer)
                    page_qty_acum = qty_acum
                    page_value_acum = value_acum
                result_index += 1

        for layer in page:
            balance = {
                'qty_balance': layer['_wac_running_qty'],
                'value_balance': layer['_wac_running_value'],
                'unit_cost': layer['_wac_running_unit_cost'],
            }
            name = layer.get('picking_name') or layer.get('reference') or layer.get('description') or ''
            lines.append({
                'id': report._get_generic_line_id('stock.valuation.layer', layer['id'], parent_line_id=parent_id),
                'parent_id': parent_id,
                'name': name,
                'columns': self._build_layer_columns_fast(report, options, layer, balance, user_tz, movement_types, qd, pd, cur, uom_name, True),
                'level': 3,
                'caret_options': 'stock.valuation.layer',
            })

        return {
            'lines': lines,
            'offset_increment': len(page),
            'has_more': has_more,
            'progress': {
                'initial_qty': str(initial_qty),
                'initial_value': str(initial_value),
                'wac_qty': str(page_qty_acum),
                'wac_value': str(page_value_acum),
            },
        }

    def _build_columns(self, report, options, data, cache, show_cost):
        cols = []
        qd = cache['qty_digits']
        pd = cache['price_digits']
        cur = cache['currency']
        fk = next(iter(data.keys()), None)
        src = data.get(fk, {})
        for col in options['columns']:
            expr = col['expression_label']
            if expr in ('qty_in', 'qty_out', 'qty_balance'):
                cols.append(report._build_column_dict(src.get(expr, 0), col, options=options, digits=qd))
            elif expr in ('value_in', 'value_out', 'value_balance'):
                cols.append(report._build_column_dict(src.get(expr, 0), col, options=options, currency=cur))
            elif expr == 'unit_cost_balance' and show_cost:
                cols.append(report._build_column_dict(src.get('unit_cost_balance', 0), col, options=options, digits=pd))
            else:
                cols.append(report._build_column_dict(None, col, options=options))
        return cols

    def _build_balance_columns(self, report, options, balance, cache):
        cols = []
        qd = cache['qty_digits']
        pd = cache['price_digits']
        cur = cache['currency']
        for col in options['columns']:
            expr = col['expression_label']
            if expr == 'qty_balance':
                cols.append(report._build_column_dict(balance.get('qty_balance', 0), col, options=options, digits=qd))
            elif expr == 'unit_cost_balance':
                cols.append(report._build_column_dict(balance.get('unit_cost', 0), col, options=options, digits=pd))
            elif expr == 'value_balance':
                cols.append(report._build_column_dict(balance.get('value_balance', 0), col, options=options, currency=cur))
            else:
                cols.append(report._build_column_dict(None, col, options=options))
        return cols

    def _build_layer_columns_fast(self, report, options, layer, balance, user_tz, movement_types, qd, pd, cur, uom_name, use_accounting_date=False):
        cols = []
        qty = layer.get('quantity', 0) or 0
        val = layer.get('value', 0) or 0
        if use_accounting_date and '_wac_unit_cost' in layer:
            cost = layer.get('_wac_unit_cost') or 0
            move_value = layer.get('_wac_move_value') or 0
        else:
            cost = layer.get('unit_cost', 0) or 0
            move_value = val
        is_in = qty > 0 or (qty == 0 and val > 0)
        is_out = qty < 0 or (qty == 0 and val < 0)
        for col in options['columns']:
            expr = col['expression_label']
            v = d = cc = None
            if expr == 'date':
                dt_val = layer.get('svl_date')
                if dt_val:
                    if isinstance(dt_val, str):
                        dt_val = datetime.strptime(dt_val, '%Y-%m-%d %H:%M:%S')
                    dt_utc = pytz.UTC.localize(dt_val) if dt_val.tzinfo is None else dt_val
                    v = dt_utc.astimezone(user_tz).date()
            elif expr == 'origin':
                v = layer.get('origin') or ''
            elif expr == 'move_type':
                mt = layer.get('movement_type')
                v = movement_types.get(mt, mt or '') if mt else ''
            elif expr == 'uom':
                v = uom_name
            elif expr == 'qty_in':
                v, d = (qty, qd) if is_in and qty else (0.0, qd)
            elif expr == 'unit_cost_in':
                v, d = (cost, pd) if is_in else (0.0, pd)
            elif expr == 'value_in':
                v, cc = (move_value, cur) if is_in else (0.0, cur)
            elif expr == 'qty_out':
                v, d = (abs(qty), qd) if is_out and qty else (0.0, qd)
            elif expr == 'unit_cost_out':
                v, d = (abs(cost), pd) if is_out else (0.0, pd)
            elif expr == 'value_out':
                v, cc = (abs(move_value), cur) if is_out else (0.0, cur)
            elif expr == 'qty_balance':
                v, d = balance.get('qty_balance', 0), qd
            elif expr == 'unit_cost_balance':
                v, d = balance.get('unit_cost', 0), pd
            elif expr == 'value_balance':
                v, cc = balance.get('value_balance', 0), cur
            cols.append(report._build_column_dict(v, col, options=options, digits=d, currency=cc))
        return cols

    def _extract_model_id(self, report, line_id, model):
        for _, m, rid in report._parse_line_id(line_id):
            if m == model:
                return rid
        return None

    def _get_context_from_line(self, line_id):
        ctx = {'product_id': None, 'lot_id': None, 'svl_id': None, 'category_id': None}
        for _, m, rid in self.env['account.report']._parse_line_id(line_id):
            if m == 'product.product':
                ctx['product_id'] = rid
            elif m == 'stock.lot':
                ctx['lot_id'] = rid
            elif m == 'stock.valuation.layer':
                ctx['svl_id'] = rid
            elif m == 'product.category':
                ctx['category_id'] = rid
        return ctx

    def _build_domain_from_context(self, ctx, options, model='stock.valuation.layer'):
        cids = self._get_company_ids(options)
        df, dt = self._get_date_range_orm(options)
        if model == 'stock.valuation.layer':
            domain = [
                ('create_date', '>=', df),
                ('create_date', '<=', dt),
                ('company_id', 'in', list(cids)),
            ]
            if ctx.get('product_id'):
                domain.append(('product_id', '=', ctx['product_id']))
            if ctx.get('lot_id'):
                domain.append(('lot_id', '=', ctx['lot_id']))
            if ctx.get('category_id'):
                products = self.env['product.product'].search([
                    ('product_tmpl_id.categ_id', 'child_of', ctx['category_id']),
                    ('product_tmpl_id.is_storable', '=', True),
                ])
                domain.append(('product_id', 'in', products.ids))
        elif model in ('stock.move', 'stock.move.line'):
            domain = [
                ('date', '>=', df),
                ('date', '<=', dt),
                ('state', '=', 'done'),
                ('company_id', 'in', list(cids)),
            ]
            if ctx.get('product_id'):
                domain.append(('product_id', '=', ctx['product_id']))
            if ctx.get('lot_id') and model == 'stock.move.line':
                domain.append(('lot_id', '=', ctx['lot_id']))
            if ctx.get('category_id'):
                products = self.env['product.product'].search([
                    ('product_tmpl_id.categ_id', 'child_of', ctx['category_id']),
                    ('product_tmpl_id.is_storable', '=', True),
                ])
                domain.append(('product_id', 'in', products.ids))
        elif model == 'product.product':
            domain = [
                ('product_tmpl_id.is_storable', '=', True),
                ('company_id', 'in', list(cids) + [False]),
            ]
            if ctx.get('category_id'):
                domain.append(('product_tmpl_id.categ_id', 'child_of', ctx['category_id']))
        else:
            domain = [('company_id', 'in', list(cids))]
        return domain

    def _notification(self, title, message, notif_type='warning'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notif_type,
                'sticky': False,
            }
        }

    def open_record(self, options, params):
        m, rid = self.env['account.report']._get_model_info_from_id(params['line_id'])
        if not m or not rid:
            return self._notification(_('No Record'), _('No record found for this line.'))
        record = self.env[m].browse(rid)
        if not record.exists():
            return self._notification(_('Record Not Found'), _('The record no longer exists.'))
        return {
            'name': record.display_name,
            'type': 'ir.actions.act_window',
            'res_model': m,
            'res_id': rid,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def open_products(self, options, params):
        ctx = self._get_context_from_line(params['line_id'])
        domain = self._build_domain_from_context(ctx, options, 'product.product')
        product_count = self.env['product.product'].search_count(domain)
        if not product_count:
            return self._notification(_('No Products'), _('No products found for the selected criteria.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Products'),
            'res_model': 'product.product',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
        }

    def open_svl(self, options, params):
        ctx = self._get_context_from_line(params['line_id'])
        domain = self._build_domain_from_context(ctx, options)
        svl_count = self.env['stock.valuation.layer'].search_count(domain)
        if not svl_count:
            return self._notification(_('No Valuation Layers'), _('No valuation layers found for the selected criteria.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Valuation Layers'),
            'res_model': 'stock.valuation.layer',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
        }

    def open_journal_entries(self, options, params):
        ctx = self._get_context_from_line(params['line_id'])
        cids = self._get_company_ids(options)
        df, dt = self._get_date_range_orm(options)
        query = """
            SELECT DISTINCT svl.account_move_id 
            FROM stock_valuation_layer svl
            JOIN product_product pp ON pp.id = svl.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE svl.create_date >= %s AND svl.create_date <= %s
              AND svl.company_id IN %s
              AND svl.account_move_id IS NOT NULL
              AND pt.is_storable = true
        """
        query_params = [df, dt, tuple(cids)]
        if ctx.get('product_id'):
            query += " AND svl.product_id = %s"
            query_params.append(ctx['product_id'])
        if ctx.get('lot_id'):
            query += " AND svl.lot_id = %s"
            query_params.append(ctx['lot_id'])
        if ctx.get('category_id'):
            query += " AND pt.categ_id IN %s"
            all_cats = self._get_category_children(ctx['category_id'])
            query_params.append(tuple(all_cats) if all_cats else (0,))
        self.env.cr.execute(query, query_params)
        move_ids = [r[0] for r in self.env.cr.fetchall()]
        if not move_ids:
            return self._notification(_('No Journal Entries'), _('No journal entries found for the selected criteria.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', move_ids)],
        }

    def open_stock_moves(self, options, params):
        ctx = self._get_context_from_line(params['line_id'])
        domain = self._build_domain_from_context(ctx, options, 'stock.move')
        move_count = self.env['stock.move'].search_count(domain)
        if not move_count:
            return self._notification(_('No Stock Moves'), _('No stock moves found for the selected criteria.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Moves'),
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
        }

    def open_stock_move_lines(self, options, params):
        ctx = self._get_context_from_line(params['line_id'])
        domain = self._build_domain_from_context(ctx, options, 'stock.move.line')
        line_count = self.env['stock.move.line'].search_count(domain)
        if not line_count:
            return self._notification(_('No Stock Move Lines'), _('No stock move lines found for the selected criteria.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Move Lines'),
            'res_model': 'stock.move.line',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
        }

    def open_journal_entry(self, options, params):
        m, rid = self.env['account.report']._get_model_info_from_id(params['line_id'])
        if m != 'stock.valuation.layer' or not rid:
            return self._notification(_('Invalid Selection'), _('Please select a valuation layer line.'))
        self.env.cr.execute("SELECT account_move_id FROM stock_valuation_layer WHERE id = %s", [rid])
        row = self.env.cr.fetchone()
        if not row or not row[0]:
            return self._notification(_('No Journal Entry'), _('This valuation layer does not have an associated journal entry.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'res_id': row[0],
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def open_stock_move(self, options, params):
        m, rid = self.env['account.report']._get_model_info_from_id(params['line_id'])
        if m != 'stock.valuation.layer' or not rid:
            return self._notification(_('Invalid Selection'), _('Please select a valuation layer line.'))
        self.env.cr.execute("SELECT stock_move_id FROM stock_valuation_layer WHERE id = %s", [rid])
        row = self.env.cr.fetchone()
        if not row or not row[0]:
            return self._notification(_('No Stock Move'), _('This valuation layer does not have an associated stock move.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Move'),
            'res_model': 'stock.move',
            'res_id': row[0],
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def open_stock_move_line(self, options, params):
        m, rid = self.env['account.report']._get_model_info_from_id(params['line_id'])
        if m != 'stock.valuation.layer' or not rid:
            return self._notification(_('Invalid Selection'), _('Please select a valuation layer line.'))
        self.env.cr.execute("""
            SELECT sml.id 
            FROM stock_move_line sml
            JOIN stock_valuation_layer svl ON svl.stock_move_id = sml.move_id
            WHERE svl.id = %s
        """, [rid])
        rows = self.env.cr.fetchall()
        if not rows:
            return self._notification(_('No Stock Move Lines'), _('This valuation layer does not have associated stock move lines.'))
        move_line_ids = [r[0] for r in rows]
        if len(move_line_ids) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Stock Move Line'),
                'res_model': 'stock.move.line',
                'res_id': move_line_ids[0],
                'view_mode': 'form',
                'views': [(False, 'form')],
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Move Lines'),
            'res_model': 'stock.move.line',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', move_line_ids)],
        }

    def open_reference(self, options, params):
        m, rid = self.env['account.report']._get_model_info_from_id(params['line_id'])
        if m != 'stock.valuation.layer' or not rid:
            return self._notification(_('Invalid Selection'), _('Please select a valuation layer line.'))
        svl = self.env['stock.valuation.layer'].browse(rid)
        if not svl.exists():
            return self._notification(_('Record Not Found'), _('The valuation layer no longer exists.'))
        if svl.stock_move_id:
            action = svl.stock_move_id.action_open_reference()
            if action and action.get('res_model') != 'stock.move':
                return action
        return {
            'res_model': 'stock.valuation.layer',
            'type': 'ir.actions.act_window',
            'views': [[False, "form"]],
            'res_id': svl.id,
        }
