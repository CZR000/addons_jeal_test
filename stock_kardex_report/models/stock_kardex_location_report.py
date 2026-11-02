from odoo import models, _
from odoo.tools.misc import get_lang
import pytz
from datetime import datetime, time


class StockKardexLocationReportHandler(models.AbstractModel):
    _name = 'stock.kardex.location.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Stock Kardex Location Report Custom Handler'

    def _get_date_field_sql(self, options):
        if options.get('use_accounting_date'):
            return "COALESCE(sml.accounting_date, sml.date)"
        return "sml.date"

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        options['display_hierarchy_filter'] = False
        options['filter_category_ids'] = previous_options.get('filter_category_ids', [])
        options['filter_product_ids'] = previous_options.get('filter_product_ids', [])
        options['filter_location_ids'] = previous_options.get('filter_location_ids', [])
        options['filter_warehouse_ids'] = previous_options.get('filter_warehouse_ids', [])
        options['group_by_category'] = previous_options.get('group_by_category', False)
        options['group_by_warehouse'] = previous_options.get('group_by_warehouse', False)
        report_ref = report.get_external_id().get(report.id, '')
        options['use_accounting_date'] = 'accounting' in report_ref.lower() or 'accounting' in (report.name or '').lower()

    def _custom_line_postprocessor(self, report, options, lines, warnings=None):
        if warnings:
            warnings.clear()
        return lines

    def _caret_options_initializer(self):
        return {
            'stock.warehouse': [
                {'name': _('Open Warehouse'), 'action': 'open_record'},
                # {'name': _('View Locations'), 'action': 'open_locations'},
                # {'name': _('View Categories'), 'action': 'open_categories'},
                # {'name': _('View Products'), 'action': 'open_products'},
                # {'name': _('View Valuation Layers'), 'action': 'open_svl'},
                # {'name': _('View Journal Entries'), 'action': 'open_journal_entries'},
                # {'name': _('View Stock Moves'), 'action': 'open_stock_moves'},
                # {'name': _('View Stock Move Lines'), 'action': 'open_stock_move_lines'},
            ],
            'stock.location': [
                {'name': _('Open Location'), 'action': 'open_record'},
                # {'name': _('View Categories'), 'action': 'open_categories'},
                # {'name': _('View Products'), 'action': 'open_products'},
                # {'name': _('View Valuation Layers'), 'action': 'open_svl'},
                # {'name': _('View Journal Entries'), 'action': 'open_journal_entries'},
                # {'name': _('View Stock Moves'), 'action': 'open_stock_moves'},
                # {'name': _('View Stock Move Lines'), 'action': 'open_stock_move_lines'},
            ],
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
            'stock.move.line': [
                {'name': _('Open Stock Move Line'), 'action': 'open_record'},
                {'name': _('Open Stock Move'), 'action': 'open_stock_move_from_sml'},
                {'name': _('Open Reference'), 'action': 'open_reference'},
                {'name': _('Open Valuation Layer'), 'action': 'open_svl_from_sml'},
                {'name': _('Open Journal Entry'), 'action': 'open_journal_entry_from_sml'},
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
        if 'movement_type' in self.env['stock.move.line']._fields:
            movement_types = dict(self.env['stock.move.line']._fields['movement_type']._description_selection(self.env))
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

    def _get_location_children(self, loc_id):
        loc = self.env['stock.location'].with_context(active_test=False).browse(loc_id)
        if not loc.exists():
            return []
        return self.env['stock.location'].with_context(active_test=False).search(
            [('parent_path', '=like', loc.parent_path + '%')]
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

    def _calc_unit_cost(self, qty_balance, value_balance):
        if qty_balance:
            return value_balance / qty_balance
        return 0.0

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        if warnings:
            warnings.clear()
        cache = self._build_cache(options)
        totals = self._init_totals(options)
        if options.get('group_by_warehouse'):
            main_lines = self._generate_warehouse_lines(report, options, totals, cache)
        else:
            main_lines = self._generate_location_lines(report, options, totals, cache)
        total_line = self._generate_total_line(report, options, totals, cache)
        return [*[(0, line) for line in main_lines], (0, total_line)]

    def _build_filters(self, options):
        """Build filter clauses and parameters separately to avoid parameter ordering issues."""
        filters = {
            'pid_filter': '',
            'cat_filter': '',
            'loc_filter': '',
            'wh_filter': '',
            'pid_params': [],
            'cat_params': [],
            'loc_params': [],
            'wh_params': [],
        }
        
        pids = options.get('filter_product_ids', [])
        catids = options.get('filter_category_ids', [])
        locids = options.get('filter_location_ids', [])
        whids = options.get('filter_warehouse_ids', [])
        
        if pids:
            filters['pid_filter'] = "AND pp.id IN %s"
            filters['pid_params'] = [tuple(pids)]
        if catids:
            all_cats = []
            for c in catids:
                all_cats.extend(self._get_category_children(c))
            if all_cats:
                filters['cat_filter'] = "AND pt.categ_id IN %s"
                filters['cat_params'] = [tuple(all_cats)]
        if locids:
            all_locs = []
            for l in locids:
                all_locs.extend(self._get_location_children(l))
            if all_locs:
                filters['loc_filter'] = "AND loc.id IN %s"
                filters['loc_params'] = [tuple(all_locs)]
        if whids:
            filters['wh_filter'] = "AND loc.warehouse_id IN %s"
            filters['wh_params'] = [tuple(whids)]
        
        return filters

    def _generate_warehouse_lines(self, report, options, totals, cache):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        filters = self._build_filters(options)
        
        query = f"""
            WITH sml_data AS (
                SELECT 
                    sml.id,
                    sml.product_id,
                    sml.location_id,
                    sml.location_dest_id,
                    loc_src.warehouse_id AS src_warehouse_id,
                    loc_dest.warehouse_id AS dest_warehouse_id,
                    sml.quantity AS qty,
                    COALESCE(sml.value, 0) AS value,
                    {date_field} AS sml_date,
                    loc_src.usage AS src_usage,
                    loc_dest.usage AS dest_usage
                FROM stock_move_line sml
                JOIN stock_move sm ON sm.id = sml.move_id
                JOIN stock_location loc_src ON loc_src.id = sml.location_id
                JOIN stock_location loc_dest ON loc_dest.id = sml.location_dest_id
                JOIN product_product pp ON pp.id = sml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE sml.state = 'done'
                  AND {date_field} <= %s
                  AND sml.company_id IN %s
                  AND pt.is_storable = true
                  {filters['pid_filter']}
                  {filters['cat_filter']}
            ),
            warehouse_agg AS (
                SELECT 
                    wh.id AS warehouse_id,
                    SUM(CASE WHEN d.dest_warehouse_id = wh.id AND d.sml_date >= %s THEN d.qty ELSE 0 END) AS qty_in,
                    SUM(CASE WHEN d.dest_warehouse_id = wh.id AND d.sml_date >= %s THEN d.value ELSE 0 END) AS value_in,
                    SUM(CASE WHEN d.src_warehouse_id = wh.id AND d.sml_date >= %s THEN d.qty ELSE 0 END) AS qty_out,
                    SUM(CASE WHEN d.src_warehouse_id = wh.id AND d.sml_date >= %s THEN ABS(d.value) ELSE 0 END) AS value_out,
                    SUM(CASE WHEN d.dest_warehouse_id = wh.id THEN d.qty ELSE 0 END) -
                    SUM(CASE WHEN d.src_warehouse_id = wh.id THEN d.qty ELSE 0 END) AS qty_balance,
                    SUM(CASE WHEN d.dest_warehouse_id = wh.id THEN d.value ELSE 0 END) -
                    SUM(CASE WHEN d.src_warehouse_id = wh.id THEN ABS(d.value) ELSE 0 END) AS value_balance
                FROM stock_warehouse wh
                JOIN sml_data d ON d.src_warehouse_id = wh.id OR d.dest_warehouse_id = wh.id
                WHERE wh.company_id IN %s
                GROUP BY wh.id
                HAVING SUM(CASE WHEN d.dest_warehouse_id = wh.id THEN d.qty ELSE 0 END) -
                       SUM(CASE WHEN d.src_warehouse_id = wh.id THEN d.qty ELSE 0 END) != 0
                    OR SUM(CASE WHEN d.sml_date >= %s THEN 1 ELSE 0 END) > 0
            )
            SELECT 
                wa.warehouse_id,
                COALESCE(wa.qty_in, 0) AS qty_in,
                COALESCE(wa.value_in, 0) AS value_in,
                COALESCE(wa.qty_out, 0) AS qty_out,
                COALESCE(wa.value_out, 0) AS value_out,
                COALESCE(wa.qty_balance, 0) AS qty_balance,
                COALESCE(wa.value_balance, 0) AS value_balance
            FROM warehouse_agg wa
            ORDER BY wa.warehouse_id
        """
        params = (
            [dt, tuple(cids)] + 
            filters['pid_params'] + 
            filters['cat_params'] + 
            [df, df, df, df, tuple(cids), df]
        )
        self.env.cr.execute(query, params)
        rows = self.env.cr.fetchall()
        if not rows:
            return []
        columns = ['warehouse_id', 'qty_in', 'value_in', 'qty_out', 'value_out', 'qty_balance', 'value_balance']
        wh_ids = [r[0] for r in rows]
        warehouses = self.env['stock.warehouse'].browse(wh_ids)
        wh_names = {w.id: w.display_name for w in warehouses}
        lines = []
        fk = next(iter(totals.keys()), None)
        for row in rows:
            row_dict = dict(zip(columns, row))
            wh_id = row_dict['warehouse_id']
            qty_balance = row_dict['qty_balance'] or 0
            value_balance = row_dict['value_balance'] or 0
            unit_cost = self._calc_unit_cost(qty_balance, value_balance)
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
            lid = report._get_generic_line_id('stock.warehouse', wh_id)
            lines.append({
                'id': lid,
                'name': wh_names.get(wh_id, ''),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': 1,
                'unfoldable': True,
                'unfolded': lid in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_warehouse',
                'caret_options': 'stock.warehouse',
            })
            totals[fk]['qty_in'] += data[fk]['qty_in']
            totals[fk]['value_in'] += data[fk]['value_in']
            totals[fk]['qty_out'] += data[fk]['qty_out']
            totals[fk]['value_out'] += data[fk]['value_out']
            totals[fk]['qty_balance'] += data[fk]['qty_balance']
            totals[fk]['value_balance'] += data[fk]['value_balance']
        return lines

    def _generate_location_lines(self, report, options, totals, cache, parent_warehouse_id=None, parent_line_id=None):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        filters = self._build_filters(options)
        
        wh_cond = ""
        wh_cond_params = []
        if parent_warehouse_id:
            wh_cond = "AND loc.warehouse_id = %s"
            wh_cond_params = [parent_warehouse_id]
        
        query = f"""
            WITH sml_data AS (
                SELECT 
                    sml.id,
                    sml.product_id,
                    sml.location_id,
                    sml.location_dest_id,
                    sml.quantity AS qty,
                    COALESCE(sml.value, 0) AS value,
                    {date_field} AS sml_date,
                    loc_src.usage AS src_usage,
                    loc_dest.usage AS dest_usage
                FROM stock_move_line sml
                JOIN stock_move sm ON sm.id = sml.move_id
                JOIN stock_location loc_src ON loc_src.id = sml.location_id
                JOIN stock_location loc_dest ON loc_dest.id = sml.location_dest_id
                JOIN product_product pp ON pp.id = sml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE sml.state = 'done'
                  AND {date_field} <= %s
                  AND sml.company_id IN %s
                  AND pt.is_storable = true
                  {filters['pid_filter']}
                  {filters['cat_filter']}
            ),
            location_agg AS (
                SELECT 
                    loc.id AS location_id,
                    SUM(CASE WHEN d.location_dest_id = loc.id AND d.sml_date >= %s THEN d.qty ELSE 0 END) AS qty_in,
                    SUM(CASE WHEN d.location_dest_id = loc.id AND d.sml_date >= %s THEN d.value ELSE 0 END) AS value_in,
                    SUM(CASE WHEN d.location_id = loc.id AND d.sml_date >= %s THEN d.qty ELSE 0 END) AS qty_out,
                    SUM(CASE WHEN d.location_id = loc.id AND d.sml_date >= %s THEN ABS(d.value) ELSE 0 END) AS value_out,
                    SUM(CASE WHEN d.location_dest_id = loc.id THEN d.qty WHEN d.location_id = loc.id THEN -d.qty ELSE 0 END) AS qty_balance,
                    SUM(CASE WHEN d.location_dest_id = loc.id THEN d.value WHEN d.location_id = loc.id THEN -ABS(d.value) ELSE 0 END) AS value_balance
                FROM stock_location loc
                JOIN sml_data d ON d.location_id = loc.id OR d.location_dest_id = loc.id
                WHERE loc.usage = 'internal'
                  {filters['loc_filter']}
                  {filters['wh_filter']}
                  {wh_cond}
                GROUP BY loc.id
                HAVING SUM(CASE WHEN d.location_dest_id = loc.id THEN d.qty WHEN d.location_id = loc.id THEN -d.qty ELSE 0 END) != 0
                    OR SUM(CASE WHEN d.sml_date >= %s THEN 1 ELSE 0 END) > 0
            )
            SELECT 
                la.location_id,
                COALESCE(la.qty_in, 0) AS qty_in,
                COALESCE(la.value_in, 0) AS value_in,
                COALESCE(la.qty_out, 0) AS qty_out,
                COALESCE(la.value_out, 0) AS value_out,
                COALESCE(la.qty_balance, 0) AS qty_balance,
                COALESCE(la.value_balance, 0) AS value_balance
            FROM location_agg la
            ORDER BY la.location_id
        """
        params = (
            [dt, tuple(cids)] + 
            filters['pid_params'] + 
            filters['cat_params'] + 
            [df, df, df, df] + 
            filters['loc_params'] + 
            filters['wh_params'] + 
            wh_cond_params + 
            [df]
        )
        self.env.cr.execute(query, params)
        rows = self.env.cr.fetchall()
        if not rows:
            return []
        columns = ['location_id', 'qty_in', 'value_in', 'qty_out', 'value_out', 'qty_balance', 'value_balance']
        loc_ids = [r[0] for r in rows]
        locations = self.env['stock.location'].browse(loc_ids)
        loc_names = {l.id: l.complete_name for l in locations}
        lines = []
        fk = next(iter(totals.keys()), None)
        level = 2 if parent_warehouse_id else 1
        for row in rows:
            row_dict = dict(zip(columns, row))
            loc_id = row_dict['location_id']
            qty_balance = row_dict['qty_balance'] or 0
            value_balance = row_dict['value_balance'] or 0
            unit_cost = self._calc_unit_cost(qty_balance, value_balance)
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
                lid = report._get_generic_line_id('stock.location', loc_id, parent_line_id=parent_line_id)
            else:
                lid = report._get_generic_line_id('stock.location', loc_id)
            line_data = {
                'id': lid,
                'name': loc_names.get(loc_id, ''),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': level,
                'unfoldable': True,
                'unfolded': lid in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_location',
                'caret_options': 'stock.location',
            }
            if parent_line_id:
                line_data['parent_id'] = parent_line_id
            lines.append(line_data)
            if not parent_warehouse_id:
                totals[fk]['qty_in'] += data[fk]['qty_in']
                totals[fk]['value_in'] += data[fk]['value_in']
                totals[fk]['qty_out'] += data[fk]['qty_out']
                totals[fk]['value_out'] += data[fk]['value_out']
                totals[fk]['qty_balance'] += data[fk]['qty_balance']
                totals[fk]['value_balance'] += data[fk]['value_balance']
        return lines

    def _generate_total_line(self, report, options, totals, cache):
        return {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('Total'),
            'level': 1,
            'columns': self._build_columns(report, options, totals, cache, False),
        }

    def _report_expand_unfoldable_line_warehouse(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        report = self.env['account.report'].browse(options['report_id'])
        wh_id = self._extract_model_id(report, line_dict_id, 'stock.warehouse')
        if not wh_id:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        cache = self._build_cache(options)
        totals = self._init_totals(options)
        lines = self._generate_location_lines(report, options, totals, cache, parent_warehouse_id=wh_id, parent_line_id=line_dict_id)
        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}

    def _report_expand_unfoldable_line_location(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        report = self.env['account.report'].browse(options['report_id'])
        loc_id = self._extract_model_id(report, line_dict_id, 'stock.location')
        if not loc_id:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        cache = self._build_cache(options)
        totals = self._init_totals(options)
        if options.get('group_by_category'):
            lines = self._generate_category_lines(report, options, totals, cache, parent_loc_id=loc_id, parent_line_id=line_dict_id)
        else:
            lines = self._generate_product_lines(report, options, totals, cache, parent_loc_id=loc_id, parent_line_id=line_dict_id)
        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}

    def _generate_category_lines(self, report, options, totals, cache, parent_loc_id, parent_line_id):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        filters = self._build_filters(options)
        
        query = f"""
            WITH sml_data AS (
                SELECT 
                    sml.product_id,
                    pt.categ_id,
                    sml.location_id,
                    sml.location_dest_id,
                    sml.quantity AS qty,
                    COALESCE(sml.value, 0) AS value,
                    {date_field} AS sml_date
                FROM stock_move_line sml
                JOIN stock_move sm ON sm.id = sml.move_id
                JOIN product_product pp ON pp.id = sml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE sml.state = 'done'
                  AND {date_field} <= %s
                  AND sml.company_id IN %s
                  AND pt.is_storable = true
                  AND (sml.location_id = %s OR sml.location_dest_id = %s)
                  {filters['pid_filter']}
                  {filters['cat_filter']}
            )
            SELECT 
                categ_id,
                SUM(CASE WHEN location_dest_id = %s AND sml_date >= %s THEN qty ELSE 0 END) AS qty_in,
                SUM(CASE WHEN location_dest_id = %s AND sml_date >= %s THEN value ELSE 0 END) AS value_in,
                SUM(CASE WHEN location_id = %s AND sml_date >= %s THEN qty ELSE 0 END) AS qty_out,
                SUM(CASE WHEN location_id = %s AND sml_date >= %s THEN ABS(value) ELSE 0 END) AS value_out,
                SUM(CASE WHEN location_dest_id = %s THEN qty WHEN location_id = %s THEN -qty ELSE 0 END) AS qty_balance,
                SUM(CASE WHEN location_dest_id = %s THEN value WHEN location_id = %s THEN -ABS(value) ELSE 0 END) AS value_balance
            FROM sml_data
            GROUP BY categ_id
            HAVING SUM(CASE WHEN location_dest_id = %s THEN qty WHEN location_id = %s THEN -qty ELSE 0 END) != 0
                OR SUM(CASE WHEN sml_date >= %s THEN 1 ELSE 0 END) > 0
            ORDER BY categ_id
        """
        params = (
            [dt, tuple(cids), parent_loc_id, parent_loc_id] + 
            filters['pid_params'] + 
            filters['cat_params'] + 
            [parent_loc_id, df, parent_loc_id, df, parent_loc_id, df, parent_loc_id, df,
             parent_loc_id, parent_loc_id, parent_loc_id, parent_loc_id, parent_loc_id, parent_loc_id, df]
        )
        self.env.cr.execute(query, params)
        rows = self.env.cr.fetchall()
        if not rows:
            return []
        columns = ['categ_id', 'qty_in', 'value_in', 'qty_out', 'value_out', 'qty_balance', 'value_balance']
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
            unit_cost = self._calc_unit_cost(qty_balance, value_balance)
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
            lid = report._get_generic_line_id('product.category', categ_id, parent_line_id=parent_line_id)
            lines.append({
                'id': lid,
                'parent_id': parent_line_id,
                'name': categ_names.get(categ_id, ''),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': 3,
                'unfoldable': True,
                'unfolded': lid in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_category',
                'caret_options': 'product.category',
            })
        return lines

    def _report_expand_unfoldable_line_category(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        report = self.env['account.report'].browse(options['report_id'])
        loc_id = self._extract_model_id(report, line_dict_id, 'stock.location')
        categ_id = self._extract_model_id(report, line_dict_id, 'product.category')
        if not loc_id or not categ_id:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        cache = self._build_cache(options)
        totals = self._init_totals(options)
        lines = self._generate_product_lines(report, options, totals, cache, parent_loc_id=loc_id, parent_line_id=line_dict_id, parent_categ_id=categ_id)
        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}

    def _generate_product_lines(self, report, options, totals, cache, parent_loc_id, parent_line_id, parent_categ_id=None):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        filters = self._build_filters(options)
        
        categ_cond = ""
        categ_params = []
        if parent_categ_id:
            categ_cond = "AND pt.categ_id = %s"
            categ_params = [parent_categ_id]
        
        query = f"""
            WITH sml_data AS (
                SELECT 
                    sml.product_id,
                    sml.location_id,
                    sml.location_dest_id,
                    sml.quantity AS qty,
                    COALESCE(sml.value, 0) AS value,
                    {date_field} AS sml_date
                FROM stock_move_line sml
                JOIN stock_move sm ON sm.id = sml.move_id
                JOIN product_product pp ON pp.id = sml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE sml.state = 'done'
                  AND {date_field} <= %s
                  AND sml.company_id IN %s
                  AND pt.is_storable = true
                  AND (sml.location_id = %s OR sml.location_dest_id = %s)
                  {filters['pid_filter']}
                  {filters['cat_filter']}
                  {categ_cond}
            )
            SELECT 
                product_id,
                SUM(CASE WHEN location_dest_id = %s AND sml_date >= %s THEN qty ELSE 0 END) AS qty_in,
                SUM(CASE WHEN location_dest_id = %s AND sml_date >= %s THEN value ELSE 0 END) AS value_in,
                SUM(CASE WHEN location_id = %s AND sml_date >= %s THEN qty ELSE 0 END) AS qty_out,
                SUM(CASE WHEN location_id = %s AND sml_date >= %s THEN ABS(value) ELSE 0 END) AS value_out,
                SUM(CASE WHEN location_dest_id = %s THEN qty WHEN location_id = %s THEN -qty ELSE 0 END) AS qty_balance,
                SUM(CASE WHEN location_dest_id = %s THEN value WHEN location_id = %s THEN -ABS(value) ELSE 0 END) AS value_balance
            FROM sml_data
            GROUP BY product_id
            HAVING SUM(CASE WHEN location_dest_id = %s THEN qty WHEN location_id = %s THEN -qty ELSE 0 END) != 0
                OR SUM(CASE WHEN sml_date >= %s THEN 1 ELSE 0 END) > 0
            ORDER BY product_id
        """
        params = (
            [dt, tuple(cids), parent_loc_id, parent_loc_id] + 
            filters['pid_params'] + 
            filters['cat_params'] + 
            categ_params + 
            [parent_loc_id, df, parent_loc_id, df, parent_loc_id, df, parent_loc_id, df,
             parent_loc_id, parent_loc_id, parent_loc_id, parent_loc_id, parent_loc_id, parent_loc_id, df]
        )
        self.env.cr.execute(query, params)
        rows = self.env.cr.fetchall()
        if not rows:
            return []
        columns = ['product_id', 'qty_in', 'value_in', 'qty_out', 'value_out', 'qty_balance', 'value_balance']
        product_ids = [r[0] for r in rows]
        products = self.env['product.product'].browse(product_ids)
        product_names = {p.id: p.display_name for p in products}
        product_lot_valuated = {p.id: p.lot_valuated for p in products}
        lines = []
        fk = next(iter(totals.keys()), None)
        level = 4 if parent_categ_id else 3
        for row in rows:
            row_dict = dict(zip(columns, row))
            pid = row_dict['product_id']
            qty_balance = row_dict['qty_balance'] or 0
            value_balance = row_dict['value_balance'] or 0
            unit_cost = self._calc_unit_cost(qty_balance, value_balance)
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
            lid = report._get_generic_line_id('product.product', pid, parent_line_id=parent_line_id)
            lines.append({
                'id': lid,
                'parent_id': parent_line_id,
                'name': product_names.get(pid, ''),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': level,
                'unfoldable': True,
                'unfolded': lid in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_product',
                'caret_options': 'product.product',
            })
        return lines

    def _report_expand_unfoldable_line_product(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        report = self.env['account.report'].browse(options['report_id'])
        loc_id = self._extract_model_id(report, line_dict_id, 'stock.location')
        pid = self._extract_model_id(report, line_dict_id, 'product.product')
        if not loc_id or not pid:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        cache = self._build_cache(options)
        product = self.env['product.product'].browse(pid)
        lot_valuated = product.lot_valuated if product.exists() else False
        if lot_valuated:
            lines = self._expand_lot_lines(report, options, line_dict_id, loc_id, pid, cache)
            return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}
        return self._expand_sml_lines(report, options, line_dict_id, loc_id, pid, None, offset, cache)

    def _report_expand_unfoldable_line_lot(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        report = self.env['account.report'].browse(options['report_id'])
        parsed = report._parse_line_id(line_dict_id)
        loc_id = pid = lot_id = None
        no_lot = False
        for markup, model, rid in parsed:
            if model == 'stock.location':
                loc_id = rid
            elif model == 'product.product':
                pid = rid
            elif model == 'stock.lot':
                lot_id = rid
            elif markup == 'no_lot':
                no_lot = True
        if not loc_id or not pid:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        cache = self._build_cache(options)
        return self._expand_sml_lines(report, options, line_dict_id, loc_id, pid, None if no_lot else lot_id, offset, cache)

    def _expand_lot_lines(self, report, options, parent_id, loc_id, pid, cache):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        
        query = f"""
            WITH sml_data AS (
                SELECT 
                    sml.lot_id,
                    sml.location_id,
                    sml.location_dest_id,
                    sml.quantity AS qty,
                    COALESCE(sml.value, 0) AS value,
                    {date_field} AS sml_date
                FROM stock_move_line sml
                JOIN stock_move sm ON sm.id = sml.move_id
                WHERE sml.state = 'done'
                  AND sml.product_id = %s
                  AND {date_field} <= %s
                  AND sml.company_id IN %s
                  AND (sml.location_id = %s OR sml.location_dest_id = %s)
            )
            SELECT 
                lot_id,
                SUM(CASE WHEN location_dest_id = %s AND sml_date >= %s THEN qty ELSE 0 END) AS qty_in,
                SUM(CASE WHEN location_dest_id = %s AND sml_date >= %s THEN value ELSE 0 END) AS value_in,
                SUM(CASE WHEN location_id = %s AND sml_date >= %s THEN qty ELSE 0 END) AS qty_out,
                SUM(CASE WHEN location_id = %s AND sml_date >= %s THEN ABS(value) ELSE 0 END) AS value_out,
                SUM(CASE WHEN location_dest_id = %s THEN qty WHEN location_id = %s THEN -qty ELSE 0 END) AS qty_balance,
                SUM(CASE WHEN location_dest_id = %s THEN value WHEN location_id = %s THEN -ABS(value) ELSE 0 END) AS value_balance
            FROM sml_data
            GROUP BY lot_id
            HAVING SUM(CASE WHEN location_dest_id = %s THEN qty WHEN location_id = %s THEN -qty ELSE 0 END) != 0
                OR SUM(CASE WHEN sml_date >= %s THEN 1 ELSE 0 END) > 0
            ORDER BY lot_id NULLS LAST
        """
        params = [pid, dt, tuple(cids), loc_id, loc_id,
                  loc_id, df, loc_id, df, loc_id, df, loc_id, df,
                  loc_id, loc_id, loc_id, loc_id, loc_id, loc_id, df]
        self.env.cr.execute(query, params)
        rows = self.env.cr.fetchall()
        if not rows:
            return []
        columns = ['lot_id', 'qty_in', 'value_in', 'qty_out', 'value_out', 'qty_balance', 'value_balance']
        lot_ids = [r[0] for r in rows if r[0]]
        lots = self.env['stock.lot'].browse(lot_ids)
        lot_names = {l.id: l.name for l in lots}
        lines = []
        fk = next(iter(self._init_totals(options).keys()), None)
        for row in rows:
            row_dict = dict(zip(columns, row))
            lid = row_dict['lot_id']
            qty_balance = row_dict['qty_balance'] or 0
            value_balance = row_dict['value_balance'] or 0
            unit_cost = self._calc_unit_cost(qty_balance, value_balance)
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
                'name': lot_names.get(lid, _('No Lot')) if lid else _('No Lot'),
                'columns': self._build_columns(report, options, data, cache, True),
                'level': 5,
                'unfoldable': True,
                'unfolded': line_id in options.get('unfolded_lines', []) or options.get('unfold_all', False),
                'expand_function': '_report_expand_unfoldable_line_lot',
                'caret_options': 'stock.lot' if lid else None,
            })
        return lines

    def _expand_sml_lines(self, report, options, parent_id, loc_id, pid, lot_id, offset, cache):
        cids = cache['company_ids']
        df, dt = self._get_date_range_utc(options, cache)
        date_field = cache['date_field']
        lang = cache['lang']
        lot_filter = "AND sml.lot_id = %s" if lot_id else "AND sml.lot_id IS NULL" if lot_id is not None else ""
        lot_params = [lot_id] if lot_id else []
        
        base_params = [loc_id, loc_id, loc_id, loc_id, pid, df, tuple(cids), loc_id, loc_id] + lot_params
        self.env.cr.execute(f"""
            SELECT 
                COALESCE(SUM(CASE WHEN sml.location_dest_id = %s THEN sml.quantity WHEN sml.location_id = %s THEN -sml.quantity ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN sml.location_dest_id = %s THEN COALESCE(sml.value, 0) WHEN sml.location_id = %s THEN -ABS(COALESCE(sml.value, 0)) ELSE 0 END), 0)
            FROM stock_move_line sml
            JOIN stock_move sm ON sm.id = sml.move_id
            WHERE sml.state = 'done'
              AND sml.product_id = %s 
              AND {date_field} < %s
              AND sml.company_id IN %s
              AND (sml.location_id = %s OR sml.location_dest_id = %s)
              {lot_filter}
        """, base_params)
        ib_row = self.env.cr.fetchone()
        initial_qty = ib_row[0] or 0
        initial_value = ib_row[1] or 0
        initial_unit_cost = self._calc_unit_cost(initial_qty, initial_value)
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
                'level': 5,
            })
        limit = report.load_more_limit if report.load_more_limit and options.get('export_mode') != 'print' else None
        limit_clause = f"LIMIT {limit + 1}" if limit else ""
        offset_clause = f"OFFSET {offset}" if offset else ""
        query = f"""
            SELECT 
                sml.id,
                {date_field} AS sml_date,
                sml.location_id,
                sml.location_dest_id,
                sml.quantity,
                COALESCE(sml.unit_cost, 0) AS unit_cost,
                COALESCE(sml.value, 0) AS value,
                sm.reference,
                sm.origin,
                sml.movement_type,
                picking.name AS picking_name,
                loc_src.complete_name AS location_src_name,
                loc_dest.complete_name AS location_dest_name,
                {initial_qty} + SUM(CASE WHEN sml.location_dest_id = %s THEN sml.quantity WHEN sml.location_id = %s THEN -sml.quantity ELSE 0 END) OVER w AS running_qty,
                {initial_value} + SUM(CASE WHEN sml.location_dest_id = %s THEN COALESCE(sml.value, 0) WHEN sml.location_id = %s THEN -ABS(COALESCE(sml.value, 0)) ELSE 0 END) OVER w AS running_value
            FROM stock_move_line sml
            JOIN stock_move sm ON sm.id = sml.move_id
            LEFT JOIN stock_picking picking ON picking.id = sm.picking_id
            LEFT JOIN stock_location loc_src ON loc_src.id = sml.location_id
            LEFT JOIN stock_location loc_dest ON loc_dest.id = sml.location_dest_id
            WHERE sml.state = 'done'
              AND sml.product_id = %s 
              AND {date_field} >= %s AND {date_field} <= %s
              AND sml.company_id IN %s
              AND (sml.location_id = %s OR sml.location_dest_id = %s)
              {lot_filter}
            WINDOW w AS (ORDER BY {date_field}, sml.id)
            ORDER BY {date_field}, sml.id
            {limit_clause} {offset_clause}
        """
        sml_params = [loc_id, loc_id, loc_id, loc_id, pid, df, dt, tuple(cids), loc_id, loc_id] + lot_params
        self.env.cr.execute(query, sml_params)
        move_lines = self.env.cr.fetchall()
        has_more = False
        if limit and len(move_lines) > limit:
            has_more = True
            move_lines = move_lines[:limit]
        if not move_lines:
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
        columns = ['id', 'sml_date', 'location_id', 'location_dest_id', 'quantity', 'unit_cost', 'value',
                   'reference', 'origin', 'movement_type', 'picking_name', 'location_src_name', 'location_dest_name',
                   'running_qty', 'running_value']
        movement_types = cache['movement_types']
        user_tz = cache['user_tz']
        qd = cache['qty_digits']
        pd = cache['price_digits']
        cur = cache['currency']
        for line_tuple in move_lines:
            line = dict(zip(columns, line_tuple))
            running_qty = line['running_qty'] or 0
            running_value = line['running_value'] or 0
            unit_cost = self._calc_unit_cost(running_qty, running_value)
            balance = {
                'qty_balance': running_qty,
                'value_balance': running_value,
                'unit_cost': unit_cost,
            }
            is_in = line['location_dest_id'] == loc_id
            name = line.get('picking_name') or line.get('reference') or ''
            lines.append({
                'id': report._get_generic_line_id('stock.move.line', line['id'], parent_line_id=parent_id),
                'parent_id': parent_id,
                'name': name,
                'columns': self._build_sml_columns(report, options, line, balance, loc_id, is_in, user_tz, movement_types, qd, pd, cur, uom_name),
                'level': 5,
                'caret_options': 'stock.move.line',
            })
        return {
            'lines': lines,
            'offset_increment': len(move_lines),
            'has_more': has_more,
            'progress': {},
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

    def _build_sml_columns(self, report, options, line, balance, loc_id, is_in, user_tz, movement_types, qd, pd, cur, uom_name):
        cols = []
        qty = line.get('quantity', 0) or 0
        cost = line.get('unit_cost', 0) or 0
        val = line.get('value', 0) or 0
        for col in options['columns']:
            expr = col['expression_label']
            v = d = cc = None
            if expr == 'date':
                dt_val = line.get('sml_date')
                if dt_val:
                    if isinstance(dt_val, str):
                        dt_val = datetime.strptime(dt_val, '%Y-%m-%d %H:%M:%S')
                    dt_utc = pytz.UTC.localize(dt_val) if dt_val.tzinfo is None else dt_val
                    v = dt_utc.astimezone(user_tz).date()
            elif expr == 'origin':
                v = line.get('origin') or ''
            elif expr == 'location_from':
                v = line.get('location_src_name') or ''
            elif expr == 'location_to':
                v = line.get('location_dest_name') or ''
            elif expr == 'move_type':
                mt = line.get('movement_type')
                v = movement_types.get(mt, mt or '') if mt else ''
            elif expr == 'uom':
                v = uom_name
            elif expr == 'qty_in':
                v, d = (qty, qd) if is_in else (0.0, qd)
            elif expr == 'unit_cost_in':
                v, d = (cost, pd) if is_in else (0.0, pd)
            elif expr == 'value_in':
                v, cc = (val, cur) if is_in else (0.0, cur)
            elif expr == 'qty_out':
                v, d = (qty, qd) if not is_in else (0.0, qd)
            elif expr == 'unit_cost_out':
                v, d = (cost, pd) if not is_in else (0.0, pd)
            elif expr == 'value_out':
                v, cc = (abs(val), cur) if not is_in else (0.0, cur)
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
        ctx = {'product_id': None, 'lot_id': None, 'location_id': None, 'warehouse_id': None, 'category_id': None, 'sml_id': None}
        for _, m, rid in self.env['account.report']._parse_line_id(line_id):
            if m == 'product.product':
                ctx['product_id'] = rid
            elif m == 'stock.lot':
                ctx['lot_id'] = rid
            elif m == 'stock.location':
                ctx['location_id'] = rid
            elif m == 'stock.warehouse':
                ctx['warehouse_id'] = rid
            elif m == 'product.category':
                ctx['category_id'] = rid
            elif m == 'stock.move.line':
                ctx['sml_id'] = rid
        return ctx

    def _build_domain_from_context(self, ctx, options, model='stock.move.line'):
        cids = self._get_company_ids(options)
        df, dt = self._get_date_range_orm(options)
        if model == 'stock.move.line':
            domain = [
                ('date', '>=', df),
                ('date', '<=', dt),
                ('state', '=', 'done'),
                ('company_id', 'in', list(cids)),
            ]
            if ctx.get('product_id'):
                domain.append(('product_id', '=', ctx['product_id']))
            if ctx.get('lot_id'):
                domain.append(('lot_id', '=', ctx['lot_id']))
            if ctx.get('location_id'):
                domain.append('|')
                domain.append(('location_id', '=', ctx['location_id']))
                domain.append(('location_dest_id', '=', ctx['location_id']))
            if ctx.get('warehouse_id'):
                domain.append('|')
                domain.append(('location_id.warehouse_id', '=', ctx['warehouse_id']))
                domain.append(('location_dest_id.warehouse_id', '=', ctx['warehouse_id']))
            if ctx.get('category_id'):
                all_cats = self._get_category_children(ctx['category_id'])
                domain.append(('product_id.product_tmpl_id.categ_id', 'in', all_cats if all_cats else [0]))
        elif model == 'stock.move':
            domain = [
                ('date', '>=', df),
                ('date', '<=', dt),
                ('state', '=', 'done'),
                ('company_id', 'in', list(cids)),
            ]
            if ctx.get('product_id'):
                domain.append(('product_id', '=', ctx['product_id']))
            if ctx.get('location_id'):
                domain.append('|')
                domain.append(('location_id', '=', ctx['location_id']))
                domain.append(('location_dest_id', '=', ctx['location_id']))
            if ctx.get('warehouse_id'):
                domain.append('|')
                domain.append(('location_id.warehouse_id', '=', ctx['warehouse_id']))
                domain.append(('location_dest_id.warehouse_id', '=', ctx['warehouse_id']))
            if ctx.get('category_id'):
                all_cats = self._get_category_children(ctx['category_id'])
                domain.append(('product_id.product_tmpl_id.categ_id', 'in', all_cats if all_cats else [0]))
        elif model == 'stock.valuation.layer':
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
                all_cats = self._get_category_children(ctx['category_id'])
                domain.append(('product_id.product_tmpl_id.categ_id', 'in', all_cats if all_cats else [0]))
        elif model == 'stock.location':
            domain = [
                ('usage', '=', 'internal'),
                ('company_id', 'in', list(cids) + [False]),
            ]
            if ctx.get('warehouse_id'):
                domain.append(('warehouse_id', '=', ctx['warehouse_id']))
        elif model == 'product.category':
            domain = []
            if ctx.get('category_id'):
                domain.append(('id', 'child_of', ctx['category_id']))
        elif model == 'product.product':
            domain = [
                ('product_tmpl_id.is_storable', '=', True),
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

    def open_locations(self, options, params):
        ctx = self._get_context_from_line(params['line_id'])
        domain = self._build_domain_from_context(ctx, options, 'stock.location')
        loc_count = self.env['stock.location'].search_count(domain)
        if not loc_count:
            return self._notification(_('No Locations'), _('No locations found for the selected criteria.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Locations'),
            'res_model': 'stock.location',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
        }

    def open_categories(self, options, params):
        ctx = self._get_context_from_line(params['line_id'])
        cids = self._get_company_ids(options)
        df, dt = self._get_date_range_orm(options)
        query = """
            SELECT DISTINCT pt.categ_id
            FROM stock_move_line sml
            JOIN product_product pp ON pp.id = sml.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE sml.state = 'done'
              AND sml.date >= %s AND sml.date <= %s
              AND sml.company_id IN %s
              AND pt.is_storable = true
        """
        query_params = [df, dt, tuple(cids)]
        if ctx.get('location_id'):
            query += " AND (sml.location_id = %s OR sml.location_dest_id = %s)"
            query_params.extend([ctx['location_id'], ctx['location_id']])
        if ctx.get('warehouse_id'):
            query += """
                AND (
                    EXISTS (SELECT 1 FROM stock_location loc WHERE loc.id = sml.location_id AND loc.warehouse_id = %s)
                    OR EXISTS (SELECT 1 FROM stock_location loc WHERE loc.id = sml.location_dest_id AND loc.warehouse_id = %s)
                )
            """
            query_params.extend([ctx['warehouse_id'], ctx['warehouse_id']])
        self.env.cr.execute(query, query_params)
        categ_ids = [r[0] for r in self.env.cr.fetchall()]
        if not categ_ids:
            return self._notification(_('No Categories'), _('No categories found for the selected criteria.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Categories'),
            'res_model': 'product.category',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', categ_ids)],
        }

    def open_products(self, options, params):
        ctx = self._get_context_from_line(params['line_id'])
        cids = self._get_company_ids(options)
        df, dt = self._get_date_range_orm(options)
        query = """
            SELECT DISTINCT sml.product_id
            FROM stock_move_line sml
            JOIN product_product pp ON pp.id = sml.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE sml.state = 'done'
              AND sml.date >= %s AND sml.date <= %s
              AND sml.company_id IN %s
              AND pt.is_storable = true
        """
        query_params = [df, dt, tuple(cids)]
        if ctx.get('location_id'):
            query += " AND (sml.location_id = %s OR sml.location_dest_id = %s)"
            query_params.extend([ctx['location_id'], ctx['location_id']])
        if ctx.get('warehouse_id'):
            query += """
                AND (
                    EXISTS (SELECT 1 FROM stock_location loc WHERE loc.id = sml.location_id AND loc.warehouse_id = %s)
                    OR EXISTS (SELECT 1 FROM stock_location loc WHERE loc.id = sml.location_dest_id AND loc.warehouse_id = %s)
                )
            """
            query_params.extend([ctx['warehouse_id'], ctx['warehouse_id']])
        if ctx.get('category_id'):
            all_cats = self._get_category_children(ctx['category_id'])
            query += " AND pt.categ_id IN %s"
            query_params.append(tuple(all_cats) if all_cats else (0,))
        self.env.cr.execute(query, query_params)
        product_ids = [r[0] for r in self.env.cr.fetchall()]
        if not product_ids:
            return self._notification(_('No Products'), _('No products found for the selected criteria.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Products'),
            'res_model': 'product.product',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', product_ids)],
        }

    def open_svl(self, options, params):
        ctx = self._get_context_from_line(params['line_id'])
        cids = self._get_company_ids(options)
        df, dt = self._get_date_range_orm(options)
        query = """
            SELECT DISTINCT svl.id
            FROM stock_valuation_layer svl
            JOIN product_product pp ON pp.id = svl.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN stock_move sm ON sm.id = svl.stock_move_id
            WHERE svl.create_date >= %s AND svl.create_date <= %s
              AND svl.company_id IN %s
              AND pt.is_storable = true
        """
        query_params = [df, dt, tuple(cids)]
        if ctx.get('product_id'):
            query += " AND svl.product_id = %s"
            query_params.append(ctx['product_id'])
        if ctx.get('lot_id'):
            query += " AND svl.lot_id = %s"
            query_params.append(ctx['lot_id'])
        if ctx.get('location_id'):
            query += " AND (sm.location_id = %s OR sm.location_dest_id = %s)"
            query_params.extend([ctx['location_id'], ctx['location_id']])
        if ctx.get('warehouse_id'):
            query += """
                AND (
                    EXISTS (SELECT 1 FROM stock_location loc WHERE loc.id = sm.location_id AND loc.warehouse_id = %s)
                    OR EXISTS (SELECT 1 FROM stock_location loc WHERE loc.id = sm.location_dest_id AND loc.warehouse_id = %s)
                )
            """
            query_params.extend([ctx['warehouse_id'], ctx['warehouse_id']])
        if ctx.get('category_id'):
            all_cats = self._get_category_children(ctx['category_id'])
            query += " AND pt.categ_id IN %s"
            query_params.append(tuple(all_cats) if all_cats else (0,))
        self.env.cr.execute(query, query_params)
        svl_ids = [r[0] for r in self.env.cr.fetchall()]
        if not svl_ids:
            return self._notification(_('No Valuation Layers'), _('No valuation layers found for the selected criteria.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Valuation Layers'),
            'res_model': 'stock.valuation.layer',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', svl_ids)],
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
            LEFT JOIN stock_move sm ON sm.id = svl.stock_move_id
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
        if ctx.get('location_id'):
            query += " AND (sm.location_id = %s OR sm.location_dest_id = %s)"
            query_params.extend([ctx['location_id'], ctx['location_id']])
        if ctx.get('warehouse_id'):
            query += """
                AND (
                    EXISTS (SELECT 1 FROM stock_location loc WHERE loc.id = sm.location_id AND loc.warehouse_id = %s)
                    OR EXISTS (SELECT 1 FROM stock_location loc WHERE loc.id = sm.location_dest_id AND loc.warehouse_id = %s)
                )
            """
            query_params.extend([ctx['warehouse_id'], ctx['warehouse_id']])
        if ctx.get('category_id'):
            all_cats = self._get_category_children(ctx['category_id'])
            query += " AND pt.categ_id IN %s"
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

    def open_stock_move_from_sml(self, options, params):
        m, rid = self.env['account.report']._get_model_info_from_id(params['line_id'])
        if m != 'stock.move.line' or not rid:
            return self._notification(_('Invalid Selection'), _('Please select a stock move line.'))
        sml = self.env['stock.move.line'].browse(rid)
        if not sml.exists() or not sml.move_id:
            return self._notification(_('No Stock Move'), _('This line does not have an associated stock move.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Move'),
            'res_model': 'stock.move',
            'res_id': sml.move_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def open_reference(self, options, params):
        m, rid = self.env['account.report']._get_model_info_from_id(params['line_id'])
        if m != 'stock.move.line' or not rid:
            return self._notification(_('Invalid Selection'), _('Please select a stock move line.'))
        sml = self.env['stock.move.line'].browse(rid)
        if not sml.exists():
            return self._notification(_('Record Not Found'), _('The stock move line no longer exists.'))
        if sml.move_id:
            action = sml.move_id.action_open_reference()
            if action and action.get('res_model') != 'stock.move':
                return action
        return {
            'res_model': 'stock.move.line',
            'type': 'ir.actions.act_window',
            'views': [[False, "form"]],
            'res_id': sml.id,
        }

    def open_svl_from_sml(self, options, params):
        m, rid = self.env['account.report']._get_model_info_from_id(params['line_id'])
        if m != 'stock.move.line' or not rid:
            return self._notification(_('Invalid Selection'), _('Please select a stock move line.'))
        sml = self.env['stock.move.line'].browse(rid)
        if not sml.exists() or not sml.move_id:
            return self._notification(_('No Stock Move'), _('This line does not have an associated stock move.'))
        svls = self.env['stock.valuation.layer'].search([('stock_move_id', '=', sml.move_id.id)])
        if not svls:
            return self._notification(_('No Valuation Layers'), _('No valuation layers found for this stock move.'))
        if len(svls) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Valuation Layer'),
                'res_model': 'stock.valuation.layer',
                'res_id': svls[0].id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Valuation Layers'),
            'res_model': 'stock.valuation.layer',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', svls.ids)],
        }

    def open_journal_entry_from_sml(self, options, params):
        m, rid = self.env['account.report']._get_model_info_from_id(params['line_id'])
        if m != 'stock.move.line' or not rid:
            return self._notification(_('Invalid Selection'), _('Please select a stock move line.'))
        sml = self.env['stock.move.line'].browse(rid)
        if not sml.exists() or not sml.move_id:
            return self._notification(_('No Stock Move'), _('This line does not have an associated stock move.'))
        svls = self.env['stock.valuation.layer'].search([
            ('stock_move_id', '=', sml.move_id.id),
            ('account_move_id', '!=', False)
        ])
        if not svls:
            return self._notification(_('No Journal Entry'), _('No journal entry found for this stock move line.'))
        move_ids = svls.mapped('account_move_id').ids
        if len(move_ids) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Journal Entry'),
                'res_model': 'account.move',
                'res_id': move_ids[0],
                'view_mode': 'form',
                'views': [(False, 'form')],
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', move_ids)],
        }
