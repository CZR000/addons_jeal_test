# -*- coding: utf-8 -*-
from odoo import models, fields, _


class AccountTrialBalanceCustomHandler(models.AbstractModel):
    _name = 'account.trial.balance.custom.handler'
    _inherit = 'account.trial.balance.report.handler'
    _description = 'Balance de Comprobación Personalizado - Handler'

    def _get_custom_display_config(self):
        return {
            'components': {
                'AccountReportFilters': 'account_trial_balance_custom.TrialBalanceCustomFilters',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        prev = previous_options or {}

        # ─── Jerarquía activa por defecto ─────────────────────────────────────
        options['hierarchy'] = prev.get('hierarchy', True)

        # ─── Filtro 1: excluir cuentas por prefijo de código ──────────────────
        raw_prefixes = self.env.company.custom_tb_exclude_prefixes or ''
        configured_prefixes = [p.strip() for p in raw_prefixes.split(',') if p.strip()]
        options['show_filter_exclude_prefixes'] = bool(configured_prefixes)
        options['custom_exclude_prefixes'] = configured_prefixes
        options['filter_exclude_prefixes'] = prev.get('filter_exclude_prefixes', False)

        # ─── Filtro 2: excluir cuentas sin grupo contable ─────────────────────
        options['show_filter_exclude_no_group'] = True
        options['filter_exclude_no_group'] = prev.get('filter_exclude_no_group', False)

        # ─── Saldo Inicial: reemplazar por diario de apertura ─────────────────
        if not options.get('columns'):
            return

        opening_journal = self.env.company.custom_opening_journal_id
        if opening_journal:
            init_group_key = options['columns'][0]['column_group_key']
            date_from = fields.Date.from_string(options['date']['date_from'])
            fy_dates = self.env.company.compute_fiscalyear_dates(date_from)
            fy_start_str = fields.Date.to_string(fy_dates['date_from'])
            fy_end_str = fields.Date.to_string(fy_dates['date_to'])
            forced = options['column_groups'][init_group_key]['forced_options']
            # Update date in-place to preserve currency_table_period_key set by super()
            forced.setdefault('date', {}).update({
                'mode': 'range', 'date_from': fy_start_str, 'date_to': fy_end_str,
            })
            forced.update({
                'journals': [{
                    'id': opening_journal.id,
                    'model': 'account.journal',
                    'selected': True,
                    'name': opening_journal.name,
                    'type': opening_journal.type,
                }],
                'general_ledger_strict_range': True,
                'include_current_year_in_unaff_earnings': False,
            })

        # ─── Guardar clave del Saldo Final (antes de agregar columnas virtuales) ──
        # La GL no incluye column_group_key en los dicts de columna de cada línea;
        # los valores se acceden por posición. Guardamos los ÍNDICES del Saldo Final
        # en options['columns'] para usarlos luego en el generador.
        final_key = options['columns'][-1]['column_group_key']
        options['custom_saldo_final_key'] = final_key
        sf_debit_idx = None
        sf_credit_idx = None
        for i, col in enumerate(options['columns']):
            if col.get('column_group_key') == final_key:
                if col.get('expression_label') == 'debit':
                    sf_debit_idx = i
                elif col.get('expression_label') == 'credit':
                    sf_credit_idx = i
        options['custom_sf_debit_idx']  = sf_debit_idx
        options['custom_sf_credit_idx'] = sf_credit_idx

        # ─── Headers visuales (column_headers[0]) ─────────────────────────────
        # Los encabezados de grupo vienen de column_headers[0], no de column_groups.
        # NO se agregan a column_groups para evitar que el GL handler ejecute
        # queries SQL adicionales y duplique columnas en las líneas.
        options['column_headers'][0] += [
            {'name': _('Saldos Balance')},
            {'name': _('Saldos Resultado')},
        ]

        # ─── Nuevas columnas Debe/Haber ───────────────────────────────────────
        for group_key, (debit_label, credit_label) in [
            ('saldo_balance_group',   ('saldo_balance_debit',   'saldo_balance_credit')),
            ('saldo_resultado_group', ('saldo_resultado_debit', 'saldo_resultado_credit')),
        ]:
            for col_name, expr_label in [('Debe', debit_label), ('Haber', credit_label)]:
                options['columns'].append({
                    'name': col_name,
                    'column_group_key': group_key,
                    'expression_label': expr_label,
                    'figure_type': 'monetary',
                    'sortable': False,
                    'has_subgroups': False,
                    'blank_if_zero': True,
                })

    # ──────────────────────────────────────────────────────────────────────────

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        # El GL handler itera sobre options['columns'] y busca cada column_group_key
        # en eval_dict. Las columnas virtuales no existen en eval_dict; hay que
        # retirarlas antes de llamar a super() y restaurarlas después.
        _virtual_keys = {'saldo_balance_debit', 'saldo_balance_credit',
                         'saldo_resultado_debit', 'saldo_resultado_credit'}
        virtual_cols = [c for c in options['columns'] if c.get('expression_label') in _virtual_keys]
        options['columns'] = [c for c in options['columns'] if c.get('expression_label') not in _virtual_keys]

        # Índices del Saldo Final (calculados sobre las 6 columnas estándar)
        sf_d_idx = options.get('custom_sf_debit_idx')
        sf_c_idx = options.get('custom_sf_credit_idx')

        lines = super()._dynamic_lines_generator(report, options, all_column_groups_expression_totals, warnings=warnings)

        # Restaurar columnas virtuales para que el renderizado tenga 10 encabezados
        options['columns'] = options['columns'] + virtual_cols

        filter_prefixes = options.get('filter_exclude_prefixes')
        filter_no_group = options.get('filter_exclude_no_group')
        exclude_prefixes = options.get('custom_exclude_prefixes', [])

        # ─── Paso 1: recopilar modelo/id de cada línea ────────────────────────
        lines_with_info = []
        account_ids = []
        group_ids = []
        for seq, line in lines:
            model, model_id = report._get_model_info_from_id(line['id'])
            lines_with_info.append((seq, line, model, model_id))
            if model == 'account.account' and model_id:
                account_ids.append(model_id)
            elif model == 'account.group' and model_id:
                group_ids.append(model_id)

        accounts_map = (
            {a.id: a for a in self.env['account.account'].browse(account_ids)}
            if account_ids else {}
        )
        groups_map = (
            {g.id: g for g in self.env['account.group'].browse(group_ids)}
            if group_ids else {}
        )

        # ─── Paso 2: cuentas excluidas por filtros activos ────────────────────
        excluded_ids = set()
        if filter_prefixes or filter_no_group:
            for aid, account in accounts_map.items():
                if filter_prefixes and exclude_prefixes:
                    if any(account.code.startswith(p) for p in exclude_prefixes):
                        excluded_ids.add(aid)
                        continue
                if filter_no_group and not account.group_id:
                    excluded_ids.add(aid)

        # ─── Acumuladores para la línea "Resultado" ───────────────────────────
        total_bal_debit = 0.0
        total_bal_credit = 0.0
        total_res_debit = 0.0
        total_res_credit = 0.0

        result_lines = []

        for seq, line, model, model_id in lines_with_info:
            # ── Aplicar filtros existentes ─────────────────────────────────────
            if model == 'account.account' and model_id in excluded_ids:
                continue
            if filter_no_group and model == 'account.group' and not model_id:
                continue

            # ── Extraer Saldo Final por posición (la GL no pone column_group_key
            #    en los dicts de columna de la línea, solo name/no_format/class) ──
            cols = line.get('columns', [])
            sf_debit  = float(cols[sf_d_idx].get('no_format') or 0.0) if sf_d_idx is not None and sf_d_idx < len(cols) else 0.0
            sf_credit = float(cols[sf_c_idx].get('no_format') or 0.0) if sf_c_idx is not None and sf_c_idx < len(cols) else 0.0

            # ── Clasificar línea: balance (1–5) vs resultado (6–9) ─────────────
            is_balance = False
            is_resultado = False

            if model == 'account.account' and model_id:
                acct = accounts_map.get(model_id)
                if acct and acct.code:
                    is_balance   = acct.code[0] in '12345'
                    is_resultado = acct.code[0] in '6789'

            elif model == 'account.group' and model_id:
                grp = groups_map.get(model_id)
                prefix = (grp.code_prefix_start or '') if grp else ''
                if prefix:
                    is_balance   = prefix[0] in '12345'
                    is_resultado = prefix[0] in '6789'

            # ── Valores para nuevas columnas ───────────────────────────────────
            bal_d = sf_debit  if is_balance   else 0.0
            bal_c = sf_credit if is_balance   else 0.0
            res_d = sf_debit  if is_resultado else 0.0
            res_c = sf_credit if is_resultado else 0.0

            # Acumular solo desde cuentas individuales (evitar doble conteo con grupos)
            if model == 'account.account':
                total_bal_debit  += bal_d
                total_bal_credit += bal_c
                total_res_debit  += res_d
                total_res_credit += res_c

            # ── Agregar nuevas columnas a la línea ─────────────────────────────
            line['columns'] = list(cols) + [
                self._make_col(bal_d, 'saldo_balance_group',   'saldo_balance_debit'),
                self._make_col(bal_c, 'saldo_balance_group',   'saldo_balance_credit'),
                self._make_col(res_d, 'saldo_resultado_group', 'saldo_resultado_debit'),
                self._make_col(res_c, 'saldo_resultado_group', 'saldo_resultado_credit'),
            ]
            result_lines.append((seq, line))

        # Guardar totales en options para que _custom_line_postprocessor
        # pueda agregar la línea "Resultado" al final, DESPUÉS del Total.
        options['_custom_bal_diff'] = total_bal_debit  - total_bal_credit
        options['_custom_res_diff'] = total_res_debit  - total_res_credit

        return result_lines

    def _custom_line_postprocessor(self, report, options, lines):
        """Agrega la línea Resultado al final (después del Total estándar)
           y aplica el estilo de jerarquía de grupos."""
        lines = super()._custom_line_postprocessor(report, options, lines)

        bal_diff = options.pop('_custom_bal_diff', None)
        res_diff = options.pop('_custom_res_diff', None)

        if bal_diff is None or res_diff is None:
            return lines

        # Columnas estándar en blanco (las primeras 6, antes de las 4 virtuales)
        n_std = len(options.get('columns', [])) - 4
        std_blank = [
            {'name': '', 'no_format': 0.0, 'class': 'number'}
            for _ in options.get('columns', [])[:n_std]
        ]

        # Solo la columna Haber de cada sección muestra el diferencial
        resultado_cols = std_blank + [
            self._make_col(0.0,      'saldo_balance_group',   'saldo_balance_debit'),
            self._make_col(bal_diff,  'saldo_balance_group',   'saldo_balance_credit',  blank_if_zero=False),
            self._make_col(0.0,      'saldo_resultado_group', 'saldo_resultado_debit'),
            self._make_col(res_diff,  'saldo_resultado_group', 'saldo_resultado_credit', blank_if_zero=False),
        ]

        resultado_line = {
            'id': report._get_generic_line_id(None, None, markup='resultado_custom'),
            'name': _('Resultado'),
            'level': 0,
            'class': 'total',
            'columns': resultado_cols,
            'unfoldable': False,
            'unfolded': False,
        }
        lines.append(resultado_line)
        return lines

    @staticmethod
    def _make_col(value, group_key, expression_label, blank_if_zero=True):
        """Construye un dict de columna; el framework formatea 'name' vía format_value."""
        return {
            'no_format': value,
            'column_group_key': group_key,
            'expression_label': expression_label,
            'figure_type': 'monetary',
            'class': 'number',
            'blank_if_zero': blank_if_zero,
            'is_zero': value == 0.0,
        }
