import logging
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..reports.report_inv_bal_0317_0320 import (
    InvBal317ReportExcel,
    InvBal318ReportExcel,
    InvBal319ReportExcel,
    InvBal320ReportExcel,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 3.18 - Estado de Flujos de Efectivo (metodo directo)
# Cada linea de contrapartida de un asiento con efectivo (cuenta 10) aporta
# un flujo igual a -saldo. Los flujos se netean por asiento y cuenta, y se
# presentan en bruto: lo que entra (+) como cobro y lo que sale (-) como
# pago, cada uno en su linea. Se clasifican por el prefijo de la cuenta de
# contrapartida (gana el mas largo) o por la "Actividad en flujo de
# efectivo (3.18)" configurada en la cuenta. Cuentas no listadas: otros
# cobros / otros pagos de operacion.
# Los asientos del diario de diferencia de cambio de la compania no son
# cobros ni pagos: su efecto sobre la cuenta 10 se muestra en su propia
# linea ("Efecto de las variaciones en el tipo de cambio").
# ---------------------------------------------------------------------------
EFE_MAP = {
    # --- Operacion ---
    # Pagos/devoluciones a clientes restan dentro de la cobranza a clientes.
    '12': ('op_cobro_ventas', 'op_cobro_ventas'),
    '13': ('op_cobro_ventas', 'op_cobro_ventas'),
    '70': ('op_cobro_ventas', 'op_otros_pagos'),
    '74': ('op_cobro_ventas', 'op_otros_pagos'),
    '752': ('op_cobro_regalias', 'op_otros_pagos'),     # comisiones y corretajes
    '753': ('op_cobro_regalias', 'op_otros_pagos'),     # regalias
    '75': ('op_otros_cobros', 'op_otros_pagos'),
    '73': ('op_otros_cobros', 'op_otros_pagos'),
    '77': ('op_cobro_intereses', 'op_otros_pagos'),
    '776': ('op_otros_cobros', 'op_otros_pagos'),       # diferencia de cambio
    '676': ('op_otros_cobros', 'op_otros_pagos'),       # diferencia de cambio
    '20': ('op_otros_cobros', 'op_pago_proveedores'),
    '21': ('op_otros_cobros', 'op_pago_proveedores'),
    '24': ('op_otros_cobros', 'op_pago_proveedores'),
    '25': ('op_otros_cobros', 'op_pago_proveedores'),
    '26': ('op_otros_cobros', 'op_pago_proveedores'),
    '28': ('op_otros_cobros', 'op_pago_proveedores'),
    '42': ('op_otros_cobros', 'op_pago_proveedores'),
    '43': ('op_otros_cobros', 'op_pago_proveedores'),
    '60': ('op_otros_cobros', 'op_pago_proveedores'),
    '63': ('op_otros_cobros', 'op_pago_proveedores'),
    '41': ('op_otros_cobros', 'op_pago_remuneraciones'),
    '62': ('op_otros_cobros', 'op_pago_remuneraciones'),
    '40': ('op_otros_cobros', 'op_pago_tributos'),
    '64': ('op_otros_cobros', 'op_pago_tributos'),
    '67': ('op_otros_cobros', 'op_pago_intereses'),
    # --- Inversion ---
    '11': ('inv_cobro_valores', 'inv_pago_valores'),
    '30': ('inv_cobro_valores', 'inv_pago_valores'),
    '31': ('inv_cobro_valores', 'inv_pago_valores'),
    '32': ('inv_cobro_ime', 'inv_pago_ime'),
    '33': ('inv_cobro_ime', 'inv_pago_ime'),
    '34': ('inv_cobro_intang', 'inv_pago_intang'),
    '35': ('inv_otros_cobros', 'inv_otros_pagos'),
    '38': ('inv_otros_cobros', 'inv_otros_pagos'),
    # --- Financiamiento ---
    '45': ('fin_cobro_obligaciones', 'fin_pago_obligaciones'),
    '50': ('fin_cobro_acciones', 'fin_otros_pagos'),
    '51': ('fin_cobro_acciones', 'fin_otros_pagos'),
    '52': ('fin_cobro_acciones', 'fin_otros_pagos'),
    '44': ('fin_otros_cobros', 'fin_pago_dividendos'),
    '59': ('fin_otros_cobros', 'fin_pago_dividendos'),
    '49': ('fin_otros_cobros', 'fin_otros_pagos'),
    '56': ('fin_otros_cobros', 'fin_otros_pagos'),
    '57': ('fin_otros_cobros', 'fin_otros_pagos'),
    '58': ('fin_otros_cobros', 'fin_otros_pagos'),
}
EFE_DEFAULT = ('op_otros_cobros', 'op_otros_pagos')

# Actividad configurada en la cuenta -> (linea de cobro, linea de pago).
EFE_BY_ACTIVITY = {
    'operation': ('op_otros_cobros', 'op_otros_pagos'),
    'investment': ('inv_otros_cobros', 'inv_otros_pagos'),
    'financing': ('fin_otros_cobros', 'fin_otros_pagos'),
}

# Prestamos y cuentas diversas con empresas del grupo (el tercero es una de
# las companias de esta base de datos): las cuentas por cobrar diversas van
# a inversion y las por pagar diversas a financiamiento. Las comerciales
# (12, 13, 42, 43) siguen en operacion. La "Actividad en flujo de efectivo
# (3.18)" de la cuenta, si esta configurada, tiene prioridad.
EFE_INTERCOMPANY = {
    '14': 'investment',
    '16': 'investment',
    '17': 'investment',
    '44': 'financing',
    '46': 'financing',
    '47': 'financing',
}

# Conciliacion del resultado neto con el efectivo de operacion.
# Depreciacion y amortizacion: estos prefijos + las cuentas de gasto de
# depreciacion configuradas en los activos fijos (en este plan la 6841xxx).
EFE_ADJ_DEPRECIATION = ['681', '682', '683']
EFE_ADJ_SOCIAL_BENEFITS = ['629']
EFE_ADJ_PROVISIONS = ['684', '685', '686']
# Cambios en activos y pasivos de operacion: -(saldo final - saldo inicial).
EFE_WORKING_CAPITAL = [
    ('wc_cxc_com', ['12']),
    ('wc_cxc_vinc', ['13']),
    ('wc_otras_cxc', ['14', '16', '17', '19']),
    ('wc_exist', ['20', '21', '22', '23', '24', '25', '26', '27', '28', '29']),
    ('wc_gpa', ['18']),
    ('wc_cxp_com', ['42']),
    ('wc_cxp_vinc', ['43']),
    ('wc_otras_cxp', ['40', '41', '46', '47', '48']),
]

# ---------------------------------------------------------------------------
# 3.19 - Estado de Cambios en el Patrimonio Neto: columnas y sus cuentas.
# Resultados acumulados incluye ademas los resultados (clases 6-9) no
# cerrados contra la 59, igual que el 3.1.
# ---------------------------------------------------------------------------
ECPN_COLUMNS = [
    ('capital', ['50']),
    ('capital_adic', ['52']),
    ('acciones_inv', ['51']),
    ('exced_reval', ['57']),
    ('reserva_legal', ['58']),
    ('otras_reservas', ['56']),
    ('res_acum', ['59', '89']),
]

# ---------------------------------------------------------------------------
# 3.20 - Estado de Resultados por Funcion: prefijo -> linea (gana el mas
# largo). Misma agrupacion que el reporte contable "Estados de resultados
# por Funcion (PE)" de Odoo:
#   70 ventas | 74 otros ingresos operacionales | 69 costo de ventas
#   91-93 distribucion | 94 ventas | 95 administracion
#   77 ingresos financieros | 97 gastos financieros
#   776 y 976 diferencia de cambio | 71-73, 75, 76, 78 otros ingresos
#   88 impuesto a la renta
# Las cuentas por naturaleza 60-68 y la 79 (cargas imputables) que no
# tengan linea propia caen en "otros gastos": su neto es justamente lo
# NO destinado a la clase 9, asi la utilidad neta siempre es la real
# (el reporte de Odoo no las muestra, por eso puede diferir en ese monto).
# ---------------------------------------------------------------------------
FUNCTION_MAP = {
    '70': 'ventas',
    '74': 'otros_ing_op',
    '69': 'costo_ventas',
    '90': 'costo_ventas',
    '91': 'gastos_distribucion',
    '92': 'gastos_distribucion',
    '93': 'gastos_distribucion',
    '94': 'gastos_venta',
    '95': 'gastos_adm',
    '77': 'ingresos_fin',
    '776': 'dif_cambio',
    '97': 'gastos_fin',
    '976': 'dif_cambio',
    '71': 'otros_ingresos',
    '72': 'otros_ingresos',
    '73': 'otros_ingresos',
    '75': 'otros_ingresos',
    '76': 'otros_ingresos',
    '78': 'otros_ingresos',
    '87': 'participaciones',
    '88': 'impuesto_renta',
}
FUNCTION_DEFAULT = 'otros_gastos'


def _match_prefix(code, mapping):
    """Valor del prefijo mas largo de `mapping` con el que empieza `code`."""
    for length in (4, 3, 2):
        value = mapping.get(code[:length])
        if value is not None:
            return value
    return None


class PleReportInvBalBook0317To0320(models.Model):
    """Formatos 3.17 a 3.20 del Libro de Inventarios y Balances.

    Todos trabajan sobre el periodo [date_start, date_end]:
    - Saldos iniciales "despues de la apertura": saldo al dia anterior a
      date_start mas los asientos de los diarios de cierre/apertura que
      caen dentro del periodo (la reapertura de saldos no es movimiento).
    - Movimientos del periodo sin esos asientos ni el cierre de date_end.
    - Saldos finales antes del cierre de date_end (igual que 3.1 a 3.16).
    """

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_17(self):
        """Formato 3.17 - Balance de comprobacion."""
        return self._generate_single('17')

    def _prepare_report_17(self):
        self.ensure_one()
        return InvBal317ReportExcel(self, self._get_data_17())

    def action_generate_18(self):
        """Formato 3.18 - Estado de flujos de efectivo."""
        return self._generate_single('18')

    def _prepare_report_18(self):
        self.ensure_one()
        return InvBal318ReportExcel(self, self._get_data_18())

    def action_generate_19(self):
        """Formato 3.19 - Estado de cambios en el patrimonio neto."""
        return self._generate_single('19')

    def _prepare_report_19(self):
        self.ensure_one()
        return InvBal319ReportExcel(self, self._get_data_19())

    def action_generate_20(self):
        """Formato 3.20 - Estado de resultados por funcion."""
        return self._generate_single('20')

    def _prepare_report_20(self):
        self.ensure_one()
        return InvBal320ReportExcel(self, self._get_data_20())

    # ------------------------------------------------------------------
    # DATA - Formato 3.17 Balance de comprobacion
    # ------------------------------------------------------------------
    def _get_data_17(self):
        """Balance de comprobacion tomado del reporte contable "Balance de
        Comprobacion Personalizado" (account_trial_balance_custom) para el
        periodo [date_start, date_end], sin jerarquia: solo las lineas de
        cuentas (subcuentas), con sus 10 columnas tal cual las calcula el
        reporte:
          Balance inicial (Debe/Haber) | Periodo (Debe/Haber) |
          Balance final (Debe/Haber) | Saldos Balance (Debe/Haber) |
          Saldos Resultado (Debe/Haber)
        Incluye las cuentas en cero que muestra el reporte. Las filas
        TOTALES / RESULTADO se calculan sobre esas lineas.
        """
        self.ensure_one()
        lines = []
        # Se incluyen todas las cuentas que lista el reporte, aun en cero
        # (en el Excel los ceros se muestran con guion).
        for account, values in self._get_trial_balance_custom_rows():
            row = {'code': account.code or '', 'name': account.name or ''}
            row.update(zip(self.TB_CUSTOM_KEYS, values))
            lines.append(row)
        lines.sort(key=lambda r: r['code'])

        numeric = ['init_debit', 'init_credit', 'mov_debit', 'mov_credit',
                   'final_debit', 'final_credit', 'bg_asset', 'bg_liability',
                   'pl_loss', 'pl_gain']
        totals = {k: sum(r[k] for r in lines) for k in numeric}

        result = {k: 0.0 for k in ('bg_asset', 'bg_liability', 'pl_loss', 'pl_gain')}
        bg_diff = totals['bg_asset'] - totals['bg_liability']
        if bg_diff >= 0:
            result['bg_liability'] = bg_diff      # utilidad
        else:
            result['bg_asset'] = -bg_diff         # perdida
        pl_diff = totals['pl_gain'] - totals['pl_loss']
        if pl_diff >= 0:
            result['pl_loss'] = pl_diff
        else:
            result['pl_gain'] = -pl_diff
        if abs(bg_diff - pl_diff) >= 0.01:
            _logger.warning(
                'PLE Inv. y Balances 3.17 (%s): el resultado del balance (%.2f) '
                'no coincide con el de resultados (%.2f).',
                self.company_id.name, bg_diff, pl_diff,
            )

        grand = dict(totals)
        for k, v in result.items():
            grand[k] += v
        return {'lines': lines, 'totals': totals, 'result': result, 'grand_totals': grand}

    # Orden de las 10 columnas del Balance de Comprobacion Personalizado.
    TB_CUSTOM_KEYS = ('init_debit', 'init_credit', 'mov_debit', 'mov_credit',
                      'final_debit', 'final_credit', 'bg_asset', 'bg_liability',
                      'pl_loss', 'pl_gain')

    def _get_trial_balance_custom_rows(self):
        """Lineas de cuenta del "Balance de Comprobacion Personalizado" del
        periodo. Retorna [(account.account, [10 importes])]."""
        self.ensure_one()
        company = self.company_id
        report = self.env.ref(
            'account_trial_balance_custom.trial_balance_custom_report',
            raise_if_not_found=False,
        )
        if not report:
            raise UserError(_(
                'No se encontró el reporte "Balance de Comprobación '
                'Personalizado" (módulo account_trial_balance_custom).'
            ))
        report = report.with_company(company).with_context(
            allowed_company_ids=[company.id],
        )
        options = report.get_options(previous_options={
            'date': {
                'date_from': fields.Date.to_string(self.date_start),
                'date_to': fields.Date.to_string(self.date_end),
                'filter': 'custom',
                'mode': 'range',
                'period_type': 'custom',
            },
            'comparison': {'filter': 'no_comparison', 'number_period': 0},
            'hierarchy': False,
            'unfold_all': True,
            'unfolded_lines': [],
            'filter_exclude_prefixes': False,
            'filter_exclude_no_group': False,
        })
        date_opt = options.get('date') or {}
        if (date_opt.get('date_from') != fields.Date.to_string(self.date_start)
                or date_opt.get('date_to') != fields.Date.to_string(self.date_end)):
            raise UserError(_(
                'No se pudo calcular el Balance de Comprobación Personalizado '
                'del %s al %s (el reporte devolvió %s - %s).'
            ) % (self.date_start.strftime('%d/%m/%Y'), self.date_end.strftime('%d/%m/%Y'),
                 date_opt.get('date_from') or '-', date_opt.get('date_to') or '-'))

        n_cols = len(self.TB_CUSTOM_KEYS)
        rows = []
        account_ids = []
        for line in report._get_lines(options):
            model, res_id = report._get_model_info_from_id(line['id'])
            if model != 'account.account' or not res_id:
                continue
            columns = line.get('columns') or []
            if len(columns) < n_cols:
                raise UserError(_(
                    'El Balance de Comprobación Personalizado devolvió %s columnas '
                    'y se esperaban %s.'
                ) % (len(columns), n_cols))
            values = []
            for col in columns[:n_cols]:
                try:
                    values.append(float(col.get('no_format') or 0.0))
                except (TypeError, ValueError):
                    values.append(0.0)
            rows.append((res_id, values))
            account_ids.append(res_id)

        accounts = self.env['account.account'].with_company(company).browse(account_ids)
        account_by_id = {a.id: a for a in accounts}
        return [(account_by_id[res_id], values) for res_id, values in rows]

    # ------------------------------------------------------------------
    # DATA - Formato 3.18 Estado de flujos de efectivo
    # ------------------------------------------------------------------
    def _get_data_18(self):
        """Flujos de efectivo del periodo por el metodo directo, con la
        conciliacion del resultado neto (metodo indirecto).

        - Cobros y pagos en bruto (neteados solo dentro de cada asiento).
        - Sin los asientos de diferencia de cambio; su efecto sobre el
          efectivo va en su propia linea y en la conciliacion.
        - "Otros" de la conciliacion: lo que no explican las partidas
          identificadas; se registra un aviso si no es cero.
        - Importes redondeados a 2 decimales.
        """
        self.ensure_one()
        cash_accounts = self._get_accounts_by_prefix(['10'])
        values = {}
        flows = []
        fx_effect = 0.0
        fx_moves = self._efe_exchange_move_ids()

        if cash_accounts:
            params = {
                'company': self.company_id.id,
                'date_from': self.date_start,
                'date_to': self.date_end,
                'excluded': self._period_excluded_move_ids(),
                'fx': fx_moves,
                'cash': tuple(cash_accounts.ids),
                'group': self._efe_group_partner_ids(),
            }
            self.env.cr.execute("""
                WITH cash_moves AS (
                    SELECT DISTINCT aml.move_id
                      FROM account_move_line aml
                      JOIN account_move am ON am.id = aml.move_id
                     WHERE am.company_id = %(company)s
                       AND am.state = 'posted'
                       AND am.date >= %(date_from)s
                       AND am.date <= %(date_to)s
                       AND am.id NOT IN %(excluded)s
                       AND am.id NOT IN %(fx)s
                       AND aml.account_id IN %(cash)s
                ), by_move AS (
                    SELECT aml.move_id, aml.account_id,
                           COALESCE(rp.commercial_partner_id, aml.partner_id) IN %(group)s AS ic,
                           SUM(-aml.balance) AS amount
                      FROM account_move_line aml
                      LEFT JOIN res_partner rp ON rp.id = aml.partner_id
                     WHERE aml.move_id IN (SELECT move_id FROM cash_moves)
                       AND aml.account_id NOT IN %(cash)s
                     GROUP BY aml.move_id, aml.account_id,
                              COALESCE(rp.commercial_partner_id, aml.partner_id) IN %(group)s
                )
                SELECT account_id, COALESCE(ic, FALSE),
                       COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0.0),
                       COALESCE(SUM(CASE WHEN amount < 0 THEN amount END), 0.0)
                  FROM by_move
                 GROUP BY account_id, COALESCE(ic, FALSE)
            """, params)
            flows = [
                (aid, bool(ic), float(inflow or 0.0), float(outflow or 0.0))
                for aid, ic, inflow, outflow in self.env.cr.fetchall()
            ]
            accounts = self.env['account.account'].with_company(
                self.company_id
            ).browse(list({f[0] for f in flows}))
            account_by_id = {a.id: a for a in accounts}
            for aid, ic, inflow, outflow in flows:
                inflow_key, outflow_key = self._efe_flow_keys(account_by_id[aid], ic)
                if inflow:
                    values[inflow_key] = values.get(inflow_key, 0.0) + inflow
                if outflow:
                    values[outflow_key] = values.get(outflow_key, 0.0) + outflow

            # Efecto de la diferencia de cambio sobre el efectivo.
            self.env.cr.execute("""
                SELECT COALESCE(SUM(aml.balance), 0.0)
                  FROM account_move_line aml
                  JOIN account_move am ON am.id = aml.move_id
                 WHERE am.id IN %(fx)s
                   AND am.state = 'posted'
                   AND am.date >= %(date_from)s
                   AND am.date <= %(date_to)s
                   AND am.id NOT IN %(excluded)s
                   AND aml.account_id IN %(cash)s
            """, params)
            fx_effect = float(self.env.cr.fetchone()[0] or 0.0)

        def v(key):
            return values.get(key, 0.0)

        op_total = sum(v(k) for k in (
            'op_cobro_ventas', 'op_cobro_regalias', 'op_cobro_intereses', 'op_otros_cobros',
            'op_pago_proveedores', 'op_pago_remuneraciones', 'op_pago_tributos',
            'op_pago_intereses', 'op_otros_pagos'))
        inv_total = sum(v(k) for k in (
            'inv_cobro_valores', 'inv_cobro_ime', 'inv_cobro_intang', 'inv_otros_cobros',
            'inv_pago_valores', 'inv_pago_ime', 'inv_pago_intang', 'inv_otros_pagos'))
        fin_total = sum(v(k) for k in (
            'fin_cobro_acciones', 'fin_cobro_obligaciones', 'fin_otros_cobros',
            'fin_pago_obligaciones', 'fin_pago_dividendos', 'fin_otros_pagos'))
        net_change = op_total + inv_total + fin_total

        initial = self._period_initial_balances()
        cash_initial = sum(initial.get(a.id, 0.0) for a in cash_accounts)
        cash_final_books = sum(
            self._balances_by_account(self.date_end, cash_accounts.ids).values()
        ) if cash_accounts else 0.0
        cash_final = cash_initial + net_change + fx_effect
        if abs(cash_final - cash_final_books) >= 0.01:
            _logger.warning(
                'PLE Inv. y Balances 3.18 (%s): saldo final de efectivo %.2f '
                'difiere del contable %.2f.', self.company_id.name, cash_final,
                cash_final_books,
            )

        # --- Conciliacion (metodo indirecto) ---
        movements = self._period_movements()
        final_balances = self._balances_by_account(self.date_end)
        all_ids = set(movements) | set(initial) | set(final_balances)
        accounts = self.env['account.account'].with_company(
            self.company_id
        ).browse(list(all_ids))
        code_by_id = {a.id: a.code or '' for a in accounts}
        activity_by_id = {a.id: a.l10n_pe_cash_flow_activity for a in accounts}
        net_result = self._period_net_result(movements, code_by_id)

        net_mov = {aid: debit - credit for aid, (debit, credit) in movements.items()}
        dep_ids = self._efe_depreciation_account_ids(code_by_id)

        def sum_mov(prefixes, exclude=()):
            return sum(
                amount for aid, amount in net_mov.items()
                if aid not in exclude
                and code_by_id.get(aid, '').startswith(tuple(prefixes))
            )

        depreciation = sum(amount for aid, amount in net_mov.items() if aid in dep_ids)
        social_benefits = sum_mov(EFE_ADJ_SOCIAL_BENEFITS, dep_ids)
        provisions = sum_mov(EFE_ADJ_PROVISIONS, dep_ids)

        # Capital de trabajo: movimiento del periodo de las cuentas de
        # operacion (= saldo final - saldo inicial), sin las cuentas o los
        # saldos con empresas del grupo que se presentan en inversion o
        # financiamiento.
        mov_by_ic = self._efe_movements_by_account_ic()
        fx_by_ic = self._efe_movements_by_account_ic(fx_moves)
        extra_ids = {aid for aid, _ic in list(mov_by_ic) + list(fx_by_ic)} - set(code_by_id)
        if extra_ids:
            extra = self.env['account.account'].with_company(self.company_id).browse(list(extra_ids))
            code_by_id.update({a.id: a.code or '' for a in extra})
            activity_by_id.update({a.id: a.l10n_pe_cash_flow_activity for a in extra})
        wc_all_prefixes = tuple(p for _key, group in EFE_WORKING_CAPITAL for p in group)

        def is_wc(aid, ic, prefixes=wc_all_prefixes):
            code = code_by_id.get(aid, '')
            if not code.startswith(tuple(prefixes)):
                return False
            activity = activity_by_id.get(aid)
            if activity in ('investment', 'financing'):
                return False
            if not activity and ic and code[:2] in EFE_INTERCOMPANY:
                return False
            return True

        working_capital = {}
        for key, prefixes in EFE_WORKING_CAPITAL:
            working_capital[key] = -sum(
                amount for (aid, ic), amount in mov_by_ic.items()
                if is_wc(aid, ic, prefixes)
            )

        # Los asientos de diferencia de cambio no son flujo de operacion: se
        # descuenta todo su efecto que no sea resultado ni capital de trabajo
        # (efectivo, prestamos de la 45, saldos con empresas del grupo, ...).
        adj_fx = -sum(
            amount for (aid, ic), amount in fx_by_ic.items()
            if not self._is_pl_code(code_by_id.get(aid, '')) and not is_wc(aid, ic)
        )
        others = op_total - (net_result + depreciation + social_benefits + provisions
                             + adj_fx + sum(working_capital.values()))
        if abs(others) >= 0.01:
            _logger.info(
                'PLE Inv. y Balances 3.18 (%s): partidas no identificadas en la '
                'conciliacion ("Otros"): %.2f.', self.company_id.name, others,
            )

        values.update({
            'op_total': op_total, 'inv_total': inv_total, 'fin_total': fin_total,
            'net_change': net_change, 'fx_effect': fx_effect,
            'cash_initial': cash_initial, 'cash_final': cash_final,
            'net_result': net_result,
            'adj_depreciation': depreciation, 'adj_social_benefits': social_benefits,
            'adj_provisions': provisions, 'adj_fx': adj_fx, 'adj_others': others,
        })
        values.update(working_capital)
        values = {k: round(val, 2) for k, val in values.items()}
        # Las lineas visibles suman exactamente su total, aun con el redondeo.
        values['adj_others'] = round(values['op_total'] - sum(values[k] for k in (
            'net_result', 'adj_depreciation', 'adj_social_benefits', 'adj_provisions',
            'adj_fx', *working_capital)), 2)
        values['periodo_label'] = self._efe_period_label()
        values['worksheet'] = self._efe_worksheet(flows, cash_accounts, initial, movements)
        return values

    # ------------------------------------------------------------------
    # Helpers del 3.18
    # ------------------------------------------------------------------
    def _efe_worksheet(self, flows, cash_accounts, initial, movements):
        """Hoja de trabajo del 3.18 (solo Excel), por cuenta de balance
        (clases 1 a 5), como la hoja de trabajo tradicional:

        - Saldo final (A) y saldo inicial (B) del periodo, con el mismo
          criterio de cierres/aperturas que el estado (A = B + movimiento).
        - Variacion C = B - A.
        - Flujo de efectivo: lo que la cuenta aporto a los cobros y pagos
          del estado (mismos asientos, neteo y clasificacion), repartido
          por actividad. La suma de la columna es el flujo neto del 3.18.
        - Reclasificaciones y ajustes D = flujo - C: la parte de la
          variacion que no paso por caja. Incluye las contrapartidas en
          cuentas de resultados (ventas, compras, gastos devengados: la
          "reclasificacion" de la hoja tradicional) y los demas ajustes
          (IGV, provisiones, reclasificaciones entre cuentas, diferencia de
          cambio).
        - Las cuentas de resultados no tienen fila. Los cobros y pagos
          registrados directamente contra ellas (ITF, diferencia de cambio,
          redondeos) se devuelven sumados en `pl_flow` para la conciliacion.
        - Las cuentas de efectivo (10) van aparte, como control.
        - Se listan todas las cuentas de balance con saldo o flujo (las de
          saldo sin movimiento tienen C = 0).
        - Detalle por linea del estado: cuentas e importes de cada linea,
          una fila por cuenta (terceros y empresas del grupo sumados).

        `flows`: [(account_id, es_empresa_del_grupo, cobros, pagos)].
        """
        self.ensure_one()
        cash_ids = set(cash_accounts.ids)
        ids = set(initial) | set(movements) | {f[0] for f in flows}
        accounts = self.env['account.account'].with_company(
            self.company_id
        ).browse(list(ids))
        account_by_id = {a.id: a for a in accounts}

        flow_by_account = {}
        by_line = {}
        for aid, ic, inflow, outflow in flows:
            inflow_key, outflow_key = self._efe_flow_keys(account_by_id[aid], ic)
            acc_flow = flow_by_account.setdefault(aid, {'op': 0.0, 'inv': 0.0, 'fin': 0.0})
            for key, amount in ((inflow_key, inflow), (outflow_key, outflow)):
                if not amount:
                    continue
                acc_flow[key.split('_')[0]] += amount
                by_line[(key, aid)] = by_line.get((key, aid), 0.0) + amount

        rows, cash_rows = [], []
        pl_flow = {'op': 0.0, 'inv': 0.0, 'fin': 0.0, 'flow': 0.0}
        for account in accounts.sorted(lambda a: a.code or ''):
            aid = account.id
            debit, credit = movements.get(aid, (0.0, 0.0))
            initial_bal = initial.get(aid, 0.0)
            final_bal = initial_bal + debit - credit
            variation = initial_bal - final_bal
            acc_flow = flow_by_account.get(aid, {})
            op, inv, fin = (acc_flow.get(k, 0.0) for k in ('op', 'inv', 'fin'))
            flow = op + inv + fin
            if all(abs(v) < 0.005 for v in (initial_bal, final_bal, flow)):
                continue
            row = {
                'code': account.code or '',
                'name': account.name or '',
                'final': round(final_bal, 2),
                'initial': round(initial_bal, 2),
                'variation': round(variation, 2),
                'non_cash': round(flow - variation, 2),
                'flow': round(flow, 2),
                'op': round(op, 2),
                'inv': round(inv, 2),
                'fin': round(fin, 2),
            }
            if aid in cash_ids:
                cash_rows.append(row)
            elif (account.code or '')[:1] in ('1', '2', '3', '4', '5'):
                rows.append(row)
            else:
                for key in pl_flow:
                    pl_flow[key] += row[key]

        lines = {}
        for (key, aid), amount in by_line.items():
            account = account_by_id[aid]
            lines.setdefault(key, []).append({
                'code': account.code or '',
                'name': account.name or '',
                'amount': round(amount, 2),
            })
        for detail in lines.values():
            detail.sort(key=lambda r: r['code'])

        return {
            'rows': rows,
            'cash_rows': cash_rows,
            'pl_flow': {k: round(v, 2) for k, v in pl_flow.items()},
            'lines': lines,
        }

    def _efe_flow_keys(self, account, intercompany=False):
        """(linea de cobro, linea de pago) de una cuenta de contrapartida.
        Prioridad: actividad configurada en la cuenta > empresa del grupo en
        cuentas diversas (EFE_INTERCOMPANY) > prefijo de la cuenta."""
        activity = account.l10n_pe_cash_flow_activity
        if activity in EFE_BY_ACTIVITY:
            return EFE_BY_ACTIVITY[activity]
        code = account.code or ''
        if intercompany and code[:2] in EFE_INTERCOMPANY:
            return EFE_BY_ACTIVITY[EFE_INTERCOMPANY[code[:2]]]
        return _match_prefix(code, EFE_MAP) or EFE_DEFAULT

    def _efe_group_partner_ids(self):
        """Partners comerciales de las demas companias de la base de datos
        (empresas del grupo). Tupla no vacia, apta para `IN`."""
        self.ensure_one()
        companies = self.env['res.company'].sudo().search([('id', '!=', self.company_id.id)])
        ids = set(companies.partner_id.commercial_partner_id.ids)
        return tuple(ids) or (0,)

    def _efe_movements_by_account_ic(self, move_ids=None):
        """Movimiento (debe - haber) del periodo por (cuenta, es empresa del
        grupo), sin cierres/aperturas. Si se pasa `move_ids`, solo de esos
        asientos. Retorna {(account_id, bool): importe}."""
        self.ensure_one()
        query = """
            SELECT aml.account_id,
                   COALESCE(COALESCE(rp.commercial_partner_id, aml.partner_id) IN %(group)s, FALSE),
                   COALESCE(SUM(aml.debit - aml.credit), 0.0)
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
              LEFT JOIN res_partner rp ON rp.id = aml.partner_id
             WHERE am.company_id = %(company)s
               AND am.state = 'posted'
               AND am.date >= %(date_from)s
               AND am.date <= %(date_to)s
               AND am.id NOT IN %(excluded)s
        """
        params = {
            'company': self.company_id.id,
            'date_from': self.date_start,
            'date_to': self.date_end,
            'excluded': self._period_excluded_move_ids(),
            'group': self._efe_group_partner_ids(),
        }
        if move_ids is not None:
            query += " AND am.id IN %(moves)s"
            params['moves'] = tuple(move_ids) or (0,)
        query += """
             GROUP BY aml.account_id,
                      COALESCE(COALESCE(rp.commercial_partner_id, aml.partner_id) IN %(group)s, FALSE)
        """
        self.env.cr.execute(query, params)
        return {
            (aid, bool(ic)): float(amount or 0.0)
            for aid, ic, amount in self.env.cr.fetchall()
        }

    def _efe_exchange_move_ids(self):
        """Asientos del diario de diferencia de cambio de la compania en el
        periodo. Tupla no vacia, apta para `IN` / `NOT IN`."""
        self.ensure_one()
        journal = self.company_id.currency_exchange_journal_id
        ids = []
        if journal:
            ids = self.env['account.move'].search([
                ('company_id', '=', self.company_id.id),
                ('journal_id', '=', journal.id),
                ('state', '=', 'posted'),
                ('date', '>=', self.date_start),
                ('date', '<=', self.date_end),
            ]).ids
        return tuple(ids) or (0,)

    def _efe_depreciation_account_ids(self, code_by_id):
        """Cuentas de gasto de depreciacion y amortizacion: prefijos
        EFE_ADJ_DEPRECIATION + las configuradas en los activos fijos."""
        self.ensure_one()
        ids = {
            aid for aid, code in code_by_id.items()
            if code.startswith(tuple(EFE_ADJ_DEPRECIATION))
        }
        if 'account.asset' in self.env:
            assets = self.env['account.asset'].with_context(active_test=False).search([
                ('company_id', '=', self.company_id.id),
            ])
            ids |= set(assets.account_depreciation_expense_id.ids)
        return ids

    def _efe_period_label(self):
        """'Ejercicio' si el rango es el ejercicio completo; si no, 'Período'."""
        self.ensure_one()
        fy = self.company_id.compute_fiscalyear_dates(self.date_end)
        if self.date_start == fy['date_from'] and self.date_end == fy['date_to']:
            return 'Ejercicio'
        return 'Período'

    # ------------------------------------------------------------------
    # DATA - Formato 3.19 Estado de cambios en el patrimonio neto
    # ------------------------------------------------------------------
    def _get_data_19(self):
        """Saldos inicial y final por columna de patrimonio y movimientos
        del periodo. Fila 10 = utilidad neta del periodo (en resultados
        acumulados). El resto del movimiento de cada columna va a:
        4 (aportes) o 9 (reducciones) en capital, capital adicional y
        acciones de inversion; 7 en excedente de revaluacion; 11 en las
        demas. Asi el saldo final siempre es el contable.
        """
        self.ensure_one()
        initial = self._period_initial_balances()
        final = self._balances_by_account(self.date_end)
        codes = self._codes_by_account_id(set(initial) | set(final))
        net_result = self._period_net_result()

        def column_balance(balances, prefixes, include_pl):
            total = 0.0
            for account_id, amount in balances.items():
                code = codes.get(account_id, '')
                if any(code.startswith(p) for p in prefixes) or (include_pl and self._is_pl_code(code)):
                    total += amount
            return -total

        columns = {}
        for key, prefixes in ECPN_COLUMNS:
            include_pl = key == 'res_acum'
            ini = column_balance(initial, prefixes, include_pl)
            fin = column_balance(final, prefixes, include_pl)
            rows = {}
            movement = fin - ini
            if key == 'res_acum':
                rows['10'] = net_result
                movement -= net_result
            if abs(movement) >= 0.005:
                if key in ('capital', 'capital_adic', 'acciones_inv'):
                    rows['4' if movement > 0 else '9'] = movement
                elif key == 'exced_reval':
                    rows['7'] = movement
                else:
                    rows['11'] = movement
            columns[key] = {'initial': ini, 'final': fin, 'rows': rows}
        return {'columns': columns, 'net_result': net_result}

    # ------------------------------------------------------------------
    # DATA - Formato 3.20 Estado de resultados por funcion
    # ------------------------------------------------------------------
    def _get_data_20(self):
        """Estado de resultados por funcion del periodo. Ingresos en
        positivo y gastos en negativo; la utilidad neta coincide con la del
        3.18 y la fila 10 del 3.19."""
        self.ensure_one()
        movements = self._period_movements()
        codes = self._codes_by_account_id(movements)
        values = {}
        for account_id, (debit, credit) in movements.items():
            code = codes.get(account_id, '')
            if not self._is_pl_code(code):
                continue
            key = _match_prefix(code, FUNCTION_MAP) or FUNCTION_DEFAULT
            values[key] = values.get(key, 0.0) - (debit - credit)

        def v(key):
            return values.get(key, 0.0)

        total_ingresos = v('ventas') + v('otros_ing_op')
        utilidad_bruta = total_ingresos + v('costo_ventas')
        gastos_operacionales = (v('gastos_distribucion') + v('gastos_venta')
                                + v('gastos_adm'))
        utilidad_operativa = utilidad_bruta + gastos_operacionales
        otros_ing_gastos = (v('ingresos_fin') + v('gastos_fin') + v('dif_cambio')
                            + v('otros_ingresos') + v('otros_gastos'))
        antes_part = utilidad_operativa + otros_ing_gastos
        antes_extra = antes_part + v('participaciones') + v('impuesto_renta')
        utilidad_neta = antes_extra
        values.update({
            'total_ingresos': total_ingresos,
            'utilidad_bruta': utilidad_bruta,
            'gastos_operacionales': gastos_operacionales,
            'utilidad_operativa': utilidad_operativa,
            'otros_ing_gastos': otros_ing_gastos,
            'antes_part': antes_part,
            'antes_extra': antes_extra,
            'antes_minoritario': antes_extra,
            'utilidad_neta': utilidad_neta,
            'utilidad_atribuible': utilidad_neta,
        })
        return values

    # ------------------------------------------------------------------
    # Helpers del grupo (solo los usan estos formatos)
    # ------------------------------------------------------------------
    def _period_excluded_move_ids(self):
        """Asientos que no son movimiento del periodo: cierres/aperturas
        dentro del periodo + cierre de la fecha fin."""
        self.ensure_one()
        ids = set(self._get_period_closing_opening_move_ids())
        ids |= set(self._get_excluded_move_ids())
        ids.discard(0)
        return tuple(ids) or (0,)

    def _period_initial_balances(self):
        """Saldo inicial por account_id "despues de la apertura": saldo al
        dia anterior a date_start + lineas de los asientos de cierre/apertura
        del periodo (excepto el cierre de date_end, que no se considera)."""
        self.ensure_one()
        balances = self._balances_by_account(self.date_start - timedelta(days=1))
        adjust_ids = set(self._get_period_closing_opening_move_ids())
        adjust_ids -= set(self._get_excluded_move_ids())
        adjust_ids.discard(0)
        if adjust_ids:
            self.env.cr.execute("""
                SELECT account_id, COALESCE(SUM(debit - credit), 0.0)
                  FROM account_move_line
                 WHERE move_id IN %(moves)s
                 GROUP BY account_id
            """, {'moves': tuple(adjust_ids)})
            for account_id, amount in self.env.cr.fetchall():
                balances[account_id] = balances.get(account_id, 0.0) + float(amount or 0.0)
        return balances

    def _period_movements(self):
        """Movimientos del periodo por account_id: {id: (debe, haber)}."""
        self.ensure_one()
        self.env.cr.execute("""
            SELECT aml.account_id,
                   COALESCE(SUM(aml.debit), 0.0),
                   COALESCE(SUM(aml.credit), 0.0)
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE am.company_id = %(company)s
               AND am.state = 'posted'
               AND am.date >= %(date_from)s
               AND am.date <= %(date_to)s
               AND am.id NOT IN %(excluded)s
             GROUP BY aml.account_id
        """, {
            'company': self.company_id.id,
            'date_from': self.date_start,
            'date_to': self.date_end,
            'excluded': self._period_excluded_move_ids(),
        })
        return {
            account_id: (float(debit or 0.0), float(credit or 0.0))
            for account_id, debit, credit in self.env.cr.fetchall()
        }

    def _codes_by_account_id(self, account_ids):
        """{account_id: codigo} resuelto para la compania del reporte."""
        accounts = self.env['account.account'].with_company(
            self.company_id
        ).browse(list(account_ids))
        return {a.id: a.code or '' for a in accounts}

    def _sum_by_prefix(self, amounts_by_code, prefixes):
        return sum(
            amount for code, amount in amounts_by_code.items()
            if any(code.startswith(p) for p in prefixes)
        )

    def _period_net_result(self, movements=None, codes=None):
        """Utilidad (+) o perdida (-) del periodo: -(debe - haber) de las
        cuentas de resultados, sin cierres/aperturas ni la 89."""
        self.ensure_one()
        movements = movements if movements is not None else self._period_movements()
        codes = codes if codes is not None else self._codes_by_account_id(movements)
        return -sum(
            debit - credit for account_id, (debit, credit) in movements.items()
            if self._is_pl_code(codes.get(account_id, ''))
        )
