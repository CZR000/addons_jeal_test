# -*- coding: utf-8 -*-
from odoo import models


class AccountReport(models.Model):
    _inherit = 'account.report'

    def _get_options_initializers_forced_sequence_map(self):
        sequence_map = super()._get_options_initializers_forced_sequence_map()
        sequence_map[self._init_options_root_plan_groupby] = 994
        return sequence_map

    def _init_options_root_plan_groupby(self, options, previous_options):
        # Inicializar siempre las claves para que el cliente no reciba undefined
        # (evita el bug de "iter1 is not iterable" en loadDisplayNames).
        options['analytic_root_plans_groupby'] = []
        options['selected_analytic_root_plan_groupby_names'] = []
        previous_root_plans = previous_options.get('analytic_root_plans_groupby', [])
        root_plan_ids = [int(pid) for pid in previous_root_plans]
        if not root_plan_ids:
            return
        root_plans = self.env['account.analytic.plan'].with_context(active_test=False).search([
            ('id', 'in', root_plan_ids),
            ('parent_id', '=', False),
        ])
        options['analytic_root_plans_groupby'] = root_plans.ids
        options['selected_analytic_root_plan_groupby_names'] = root_plans.mapped('name')
        if not root_plans:
            return
        # Política REEMPLAZAR: las cuentas manuales se sustituyen por las
        # cuentas cuyo root_plan_id esté en la selección.
        accounts = self.env['account.analytic.account'].with_context(active_test=False).search([
            ('root_plan_id', 'in', root_plans.ids),
        ])
        previous_options['analytic_accounts_groupby'] = accounts.ids

    @staticmethod
    def _resolve_subplan_name(acc):
        """Subplan efectivo = hijo directo del root_plan_id.
        Si la cuenta cuelga directo del root (plan_id == root_plan_id)
        o no tiene root, devuelve '—'.
        """
        if not acc.root_plan_id or acc.plan_id == acc.root_plan_id:
            return '—'
        p = acc.plan_id
        while p.parent_id and p.parent_id != acc.root_plan_id:
            p = p.parent_id
        return p.name if p else '—'

    def _get_column_headers_render_data(self, options):
        render_data = super()._get_column_headers_render_data(options)
        column_headers = options.get('column_headers', [])
        if len(column_headers) < 2:
            return render_data
        analytic_level = column_headers[1]
        if not any(cell.get('forced_options', {}).get('analytic_accounts_list')
                   for cell in analytic_level):
            return render_data

        account_ids = [
            cell['forced_options']['analytic_accounts_list'][0]
            for cell in analytic_level
            if cell.get('forced_options', {}).get('analytic_accounts_list')
        ]
        accounts = self.env['account.analytic.account'].browse(account_ids)

        # Mapa acc_id -> (nombre_root, nombre_subplan_efectivo)
        accounts_map = {
            acc.id: (
                acc.root_plan_id.name if acc.root_plan_id else '',
                self._resolve_subplan_name(acc),
            )
            for acc in accounts
        }

        # Fila 1: plan raíz (colapsa contiguos con mismo root)
        root_plan_row = []
        current_root = None
        for cell in analytic_level:
            acc_tuple = cell.get('forced_options', {}).get('analytic_accounts_list')
            root_name = accounts_map.get(acc_tuple[0], ('', ''))[0] if acc_tuple else ''
            if current_root and current_root['name'] == root_name:
                current_root['colspan'] += 1
            else:
                current_root = {'name': root_name, 'colspan': 1}
                root_plan_row.append(current_root)
        render_data['root_plan_row'] = root_plan_row

        # Fila 2: subplan (colapsa contiguos con mismo (root, subplan))
        # El _key incluye el root para no fusionar visualmente subplanes
        # homónimos bajo distintos roots.
        subplan_row = []
        current_sub = None
        for cell in analytic_level:
            acc_tuple = cell.get('forced_options', {}).get('analytic_accounts_list')
            key = accounts_map.get(acc_tuple[0], ('', '')) if acc_tuple else ('', '')
            subplan_name = key[1]
            if current_sub and current_sub['_key'] == key:
                current_sub['colspan'] += 1
            else:
                current_sub = {'name': subplan_name, 'colspan': 1, '_key': key}
                subplan_row.append(current_sub)
        render_data['subplan_row'] = [
            {'name': c['name'], 'colspan': c['colspan']} for c in subplan_row
        ]

        return render_data