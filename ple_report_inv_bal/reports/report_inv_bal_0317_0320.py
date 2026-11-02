from .report_inv_bal_base import InvBalReportBase


def _period_label(obj):
    if not obj.date_start or not obj.date_end:
        return ''
    return 'DEL %s AL %s' % (obj.date_start.strftime('%d/%m/%Y'),
                             obj.date_end.strftime('%d/%m/%Y'))


class _PeriodHeaderMixin(object):
    """Cabecera estandar + linea de periodo (los formatos 3.17 a 3.20 son
    de un periodo, no a una fecha)."""

    def _write_period_header(self, ws, span_last_col):
        f = self._formats
        row = self._write_standard_header(ws, 0, span_last_col)
        ws.write_rich_string(
            row - 1, 0,
            f['hdr_lbl'], 'PERÍODO:  ',
            f['hdr_val'], _period_label(self.obj),
        )
        return row


# ===========================================================================
# 3.17 - Balance de comprobacion
# ===========================================================================
class InvBal317ReportExcel(_PeriodHeaderMixin, InvBalReportBase):
    """Formato 3.17 - Balance de comprobacion (lineas de cuenta del Balance de
    Comprobacion Personalizado de Odoo).

    `data`: {'lines': [{code, name, init_debit, init_credit, mov_debit,
    mov_credit, final_debit, final_credit, bg_asset, bg_liability, pl_loss,
    pl_gain}], 'totals', 'result', 'grand_totals'}
    """

    FORMATO_CODE = '3.17'
    FORMATO_TITLE = 'Balance de comprobación'
    SHEET_NAME = 'F3.17 Balance Comprobacion'
    LANDSCAPE = True

    NUMERIC = ['init_debit', 'init_credit', 'mov_debit', 'mov_credit',
               'final_debit', 'final_credit', 'bg_asset', 'bg_liability',
               'pl_loss', 'pl_gain']

    def build(self, ws, workbook):
        f = self._formats
        ws.set_column(0, 0, 11)
        ws.set_column(1, 1, 38)
        ws.set_column(2, 11, 14)

        row = self._write_period_header(ws, 11)

        ws.set_row(row, 30)
        ws.set_row(row + 1, 30)
        groups = [
            (0, 1, 'CUENTA Y SUBCUENTA CONTABLE'),
            (2, 3, 'SALDOS INICIALES'),
            (4, 5, 'MOVIMIENTOS'),
            (6, 7, 'SALDOS FINALES'),
            (8, 9, 'SALDOS FINALES DEL BALANCE GENERAL'),
            (10, 11, 'SALDOS FINALES DEL ESTADO DE RESULTADOS POR NATURALEZA'),
        ]
        for first, last, label in groups:
            ws.merge_range(row, first, row, last, label, f['col'])
        subs = ['CÓDIGO', 'DENOMINACIÓN', 'DEUDOR', 'ACREEDOR', 'DEBE', 'HABER',
                'DEUDOR', 'ACREEDOR', 'ACTIVO', 'PASIVO Y PATRIMONIO',
                'PÉRDIDAS', 'GANANCIAS']
        for col, label in enumerate(subs):
            ws.write(row + 1, col, label, f['col'])
        row += 2

        for line in self.data.get('lines', []):
            ws.write_string(row, 0, line.get('code') or '', f['txt'])
            ws.write_string(row, 1, line.get('name') or '', f['txt_wrap'])
            for col, key in enumerate(self.NUMERIC, start=2):
                ws.write_number(row, col, float(line.get(key) or 0.0), f['num'])
            row += 1

        for label, values in (('TOTALES', self.data.get('totals') or {}),
                              ('RESULTADO DEL EJERCICIO O PERÍODO', self.data.get('result') or {}),
                              ('TOTALES', self.data.get('grand_totals') or {})):
            ws.merge_range(row, 0, row, 1, label, f['total_lbl_right'])
            for col, key in enumerate(self.NUMERIC, start=2):
                if key in values:
                    ws.write_number(row, col, float(values.get(key) or 0.0), f['total_num'])
                else:
                    ws.write_blank(row, col, None, f['total_num'])
            row += 1


# ===========================================================================
# Base para estados de "descripcion | importe" (3.18 y 3.20)
# ===========================================================================
class _StatementReportBase(_PeriodHeaderMixin, InvBalReportBase):
    """Estado financiero de dos columnas: descripcion e importe.

    Subclases definen ROWS: lista de (tipo, etiqueta, clave) donde tipo es
    'section' | 'label' | 'line' | 'total' | 'blank'. `data` es un dict
    {clave: importe}; una clave ausente o None se imprime en blanco.
    """

    ROWS = []

    def build(self, ws, workbook):
        f = self._formats
        f['indent'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter', 'border': 1,
            'indent': 2, 'text_wrap': True,
        })
        f['label_only'] = workbook.add_format({
            'italic': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
            'border': 1, 'indent': 1,
        })
        ws.set_column(0, 0, 90)
        ws.set_column(1, 1, 20)

        row = self._write_period_header(ws, 1)
        ws.set_row(row, 22)
        ws.write(row, 0, 'DESCRIPCIÓN', f['col'])
        ws.write(row, 1, 'EJERCICIO O PERÍODO', f['col'])
        row += 1

        periodo = self.data.get('periodo_label') or 'Ejercicio'
        for kind, label, key in self.ROWS:
            label = label.replace('{periodo}', periodo)
            if kind == 'blank':
                row += 1
                continue
            if kind == 'section':
                ws.merge_range(row, 0, row, 1, label, f['section'])
                row += 1
                continue
            if kind == 'label':
                ws.write(row, 0, label, f['label_only'])
                ws.write_blank(row, 1, None, f['num'])
                row += 1
                continue
            lbl_fmt = f['total_lbl'] if kind == 'total' else f['indent']
            num_fmt = f['total_num'] if kind == 'total' else f['num']
            ws.write(row, 0, label, lbl_fmt)
            value = self.data.get(key) if key else None
            if value is None:
                ws.write_blank(row, 1, None, num_fmt)
            else:
                ws.write_number(row, 1, float(value), num_fmt)
            row += 1


# ===========================================================================
# 3.18 - Estado de flujos de efectivo
# ===========================================================================
class InvBal318ReportExcel(_StatementReportBase):
    """Formato 3.18 - Estado de flujos de efectivo (metodo directo) con la
    conciliacion del resultado neto. Pagos en negativo."""

    FORMATO_CODE = '3.18'
    FORMATO_TITLE = 'Estado de flujos de efectivo'
    SHEET_NAME = 'F3.18 Flujos de Efectivo'

    ROWS = [
        ('section', 'ACTIVIDADES DE OPERACIÓN', None),
        ('line', 'Cobranza de venta de bienes o servicios e ingresos operacionales', 'op_cobro_ventas'),
        ('line', 'Cobranza de regalías, honorarios, comisiones y otros', 'op_cobro_regalias'),
        ('line', 'Cobranza de intereses y dividendos recibidos', 'op_cobro_intereses'),
        ('line', 'Otros cobros de efectivo relativos a la actividad', 'op_otros_cobros'),
        ('label', 'Menos:', None),
        ('line', 'Pago a proveedores de bienes y servicios', 'op_pago_proveedores'),
        ('line', 'Pago de remuneraciones y beneficios sociales', 'op_pago_remuneraciones'),
        ('line', 'Pago de tributos', 'op_pago_tributos'),
        ('line', 'Pago de intereses y rendimientos', 'op_pago_intereses'),
        ('line', 'Otros pagos de efectivo relativos a la actividad', 'op_otros_pagos'),
        ('total', 'Aumento (Disminución) del Efectivo y Equivalente de Efectivo Provenientes de Actividades de Operación', 'op_total'),
        ('blank', '', None),
        ('section', 'ACTIVIDADES DE INVERSIÓN', None),
        ('line', 'Cobranza de venta de valores e inversiones permanentes', 'inv_cobro_valores'),
        ('line', 'Cobranza de venta de inmuebles, maquinaria y equipo', 'inv_cobro_ime'),
        ('line', 'Cobranza de venta de activos intangibles', 'inv_cobro_intang'),
        ('line', 'Otros cobros de efectivo relativos a la actividad', 'inv_otros_cobros'),
        ('label', 'Menos:', None),
        ('line', 'Pagos por compra de valores e inversiones permanentes', 'inv_pago_valores'),
        ('line', 'Pagos por compra de inmuebles, maquinaria y equipo', 'inv_pago_ime'),
        ('line', 'Pagos por compra de activos intangibles', 'inv_pago_intang'),
        ('line', 'Otros pagos de efectivo relativos a la actividad', 'inv_otros_pagos'),
        ('total', 'Aumento (Disminución) del Efectivo y Equivalente de Efectivo Provenientes de Actividades de Inversión', 'inv_total'),
        ('blank', '', None),
        ('section', 'ACTIVIDADES DE FINANCIAMIENTO', None),
        ('line', 'Cobranza de emisión de acciones o nuevos aportes', 'fin_cobro_acciones'),
        ('line', 'Cobranza de recursos obtenidos por emisión de valores u otras obligaciones de largo plazo', 'fin_cobro_obligaciones'),
        ('line', 'Otros cobros de efectivo relativos a la actividad', 'fin_otros_cobros'),
        ('label', 'Menos:', None),
        ('line', 'Pagos de amortización o cancelación de valores u otras obligaciones de largo plazo', 'fin_pago_obligaciones'),
        ('line', 'Pago de dividendos y otras distribuciones', 'fin_pago_dividendos'),
        ('line', 'Otros pagos de efectivo relativos a la actividad', 'fin_otros_pagos'),
        ('total', 'Aumento (Disminución) del Efectivo y Equivalente de Efectivo Provenientes de Actividades de Financiamiento', 'fin_total'),
        ('blank', '', None),
        ('total', 'Aumento (Disminución) Neto de Efectivo y Equivalente de Efectivo', 'net_change'),
        ('line', 'Efecto de las Variaciones en el Tipo de Cambio sobre el Efectivo y Equivalente de Efectivo', 'fx_effect'),
        ('total', 'Saldo Efectivo y Equivalente de Efectivo al Inicio del {periodo}', 'cash_initial'),
        ('total', 'Saldo Efectivo y Equivalente de Efectivo al Final del {periodo}', 'cash_final'),
        ('blank', '', None),
        ('section', 'CONCILIACIÓN DEL RESULTADO NETO CON EL EFECTIVO Y EQUIVALENTE DE EFECTIVO PROVENIENTE DE LAS ACTIVIDADES DE OPERACIÓN', None),
        ('total', 'Utilidad (Pérdida) neta del {periodo}', 'net_result'),
        ('label', 'Más: Ajustes a la Utilidad (Pérdida) del {periodo}', None),
        ('line', 'Depreciación y amortización del período', 'adj_depreciation'),
        ('line', 'Provisión Beneficios Sociales', 'adj_social_benefits'),
        ('line', 'Provisiones Diversas', 'adj_provisions'),
        ('line', 'Pérdida en venta de inmuebles, maquinaria y equipo', None),
        ('line', 'Pérdida en venta de valores e inversiones permanentes', None),
        ('line', 'Pérdida por activos monetarios no corrientes', None),
        ('line', 'Diferencia de cambio sobre el efectivo y equivalente de efectivo', 'adj_fx'),
        ('line', 'Otros', 'adj_others'),
        ('label', 'Menos: Ajustes a la Utilidad (Pérdida) del {periodo}', None),
        ('line', 'Utilidad en venta de inmuebles, maquinaria y equipo', None),
        ('line', 'Utilidad en venta de valores e inversiones permanentes', None),
        ('line', 'Ganancia por pasivos monetarios no corrientes', None),
        ('label', 'Cargos y Abonos por cambios netos en el Activo y Pasivo', None),
        ('line', '(Aumento) Disminución de Cuentas por Cobrar Comerciales', 'wc_cxc_com'),
        ('line', '(Aumento) Disminución de Cuentas por Cobrar Vinculadas', 'wc_cxc_vinc'),
        ('line', '(Aumento) Disminución de Otras Cuentas por Cobrar', 'wc_otras_cxc'),
        ('line', '(Aumento) Disminución en Existencias', 'wc_exist'),
        ('line', '(Aumento) Disminución en Gastos Pagados por Anticipado', 'wc_gpa'),
        ('line', 'Aumento (Disminución) de Cuentas por Pagar Comerciales', 'wc_cxp_com'),
        ('line', 'Aumento (Disminución) de Cuentas por Pagar Vinculadas', 'wc_cxp_vinc'),
        ('line', 'Aumento (Disminución) de Otras Cuentas por Pagar', 'wc_otras_cxp'),
        ('total', 'Aumento (Disminución) del Efectivo y Equivalente de Efectivo proveniente de las Actividades de Operación', 'op_total'),
    ]

    WORKSHEET_NAME = 'F3.18 Hoja de Trabajo'
    # Columnas de la hoja de trabajo: (clave, titulo, ancho)
    WS_COLUMNS = [
        ('code', 'CUENTA', 11),
        ('name', 'DENOMINACIÓN', 42),
        ('final', 'SALDO FINAL\n(A)', 16),
        ('initial', 'SALDO INICIAL\n(B)', 16),
        ('variation', 'VARIACIÓN\n(C = B - A)', 16),
        ('non_cash', 'RECLASIFICACIONES Y AJUSTES\n(D)', 17),
        ('flow', 'FLUJO DE EFECTIVO\n(C + D)', 17),
        ('op', 'OPERACIÓN', 16),
        ('inv', 'INVERSIÓN', 16),
        ('fin', 'FINANCIAMIENTO', 16),
    ]
    ACTIVITY_SECTIONS = {
        'op': 'ACTIVIDADES DE OPERACIÓN',
        'inv': 'ACTIVIDADES DE INVERSIÓN',
        'fin': 'ACTIVIDADES DE FINANCIAMIENTO',
    }

    def write_extra_sheets(self, workbook):
        """Hoja de trabajo del 3.18: de donde sale cada importe del estado."""
        data = self.data.get('worksheet')
        if not data:
            return
        ws = workbook.add_worksheet(self.WORKSHEET_NAME)
        ws.set_landscape()
        ws.set_paper(9)
        ws.set_margins(0.2, 0.2, 0.3, 0.5)
        ws.fit_to_pages(1, 0)
        f = self._formats
        f['ws_note'] = workbook.add_format({
            'italic': True, 'size': 9, 'text_wrap': True, 'valign': 'top',
        })
        f['ws_group_lbl'] = workbook.add_format({
            'bold': True, 'size': 10, 'border': 1, 'bg_color': '#EDEDED',
        })
        f['ws_group_num'] = workbook.add_format({
            'bold': True, 'size': 10, 'border': 1, 'bg_color': '#EDEDED',
            'num_format': '#,##0.00;-#,##0.00;"-"',
        })
        f['ws_check_num'] = workbook.add_format({
            'bold': True, 'size': 10, 'border': 1, 'bg_color': '#E2EFDA',
            'num_format': '#,##0.00;-#,##0.00;"-"',
        })
        last_col = len(self.WS_COLUMNS) - 1
        for col, (_key, _label, width) in enumerate(self.WS_COLUMNS):
            ws.set_column(col, col, width)

        row = self._write_worksheet_header(ws, last_col)
        row = self._write_worksheet_accounts(ws, row, data)
        row += 2
        self._write_worksheet_lines(ws, row, data)

    # ------------------------------------------------------------------
    def _write_worksheet_header(self, ws, last_col):
        f = self._formats
        company = self.obj.company_id
        ws.set_row(0, 30)
        ws.merge_range(
            0, 0, 0, last_col,
            'HOJA DE TRABAJO - FORMATO 3.18: ESTADO DE FLUJOS DE EFECTIVO',
            f['title'],
        )
        ws.write_rich_string(2, 0, f['hdr_lbl'], 'RUC:  ', f['hdr_val'], company.vat or '-')
        ws.write_rich_string(
            3, 0, f['hdr_lbl'], 'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL:  ',
            f['hdr_val'], company.name or '-',
        )
        ws.write_rich_string(4, 0, f['hdr_lbl'], 'PERÍODO:  ', f['hdr_val'], _period_label(self.obj))
        ws.set_row(5, 54)
        ws.merge_range(
            5, 0, 5, last_col,
            'Cuentas de balance (clases 1 a 5). C = B - A: variación del saldo en el '
            'período (positivo = disminución de un activo o aumento de un pasivo). '
            'D: reclasificaciones y ajustes que no pasaron por caja: contrapartidas en '
            'cuentas de resultados (ventas, compras, gastos) y otros ajustes (IGV, '
            'provisiones, reclasificaciones entre cuentas, diferencia de cambio). '
            'C + D: lo que la cuenta aportó a los cobros y pagos del estado, repartido '
            'por actividad con la misma clasificación del formato 3.18. La cuenta 10 y '
            'los cobros o pagos registrados directamente contra cuentas de resultados '
            'se muestran en la conciliación.',
            f['ws_note'],
        )
        return 7

    def _write_worksheet_accounts(self, ws, row, data):
        f = self._formats
        cols = self.WS_COLUMNS
        num_cols = range(2, len(cols))

        ws.set_row(row, 18)
        ws.set_row(row + 1, 42)
        for col in range(0, 7):
            ws.merge_range(row, col, row + 1, col, cols[col][1], f['col'])
        ws.merge_range(row, 7, row, 9, 'FLUJO POR ACTIVIDADES', f['col'])
        for col in (7, 8, 9):
            ws.write(row + 1, col, cols[col][1], f['col'])
        row += 2

        def cell(r, c):
            return '%s%d' % (chr(ord('A') + c), r + 1)

        def write_formulas(r, values, num_fmt):
            """C, D y C + D como formulas; A, B y actividades como valores."""
            ws.write_number(r, 2, values['final'], num_fmt)
            ws.write_number(r, 3, values['initial'], num_fmt)
            ws.write_formula(r, 4, '=%s-%s' % (cell(r, 3), cell(r, 2)), num_fmt, values['variation'])
            ws.write_formula(r, 5, '=%s-%s' % (cell(r, 6), cell(r, 4)), num_fmt, values['non_cash'])
            ws.write_formula(r, 6, '=SUM(%s:%s)' % (cell(r, 7), cell(r, 9)), num_fmt, values['flow'])
            for c, key in ((7, 'op'), (8, 'inv'), (9, 'fin')):
                ws.write_number(r, c, values[key], num_fmt)

        def write_subtotal(r, first, last, label, name, values, lbl_fmt, num_fmt):
            ws.write(r, 0, label, lbl_fmt)
            ws.write(r, 1, name, lbl_fmt)
            for c in num_cols:
                key = cols[c][0]
                ws.write_formula(
                    r, c, '=SUBTOTAL(9,%s:%s)' % (cell(first, c), cell(last, c)),
                    num_fmt, values.get(key, 0.0),
                )

        def sums(items):
            return {
                key: round(sum(i[key] for i in items), 2)
                for key, _l, _w in cols[2:]
            }

        # Cuentas distintas de efectivo, agrupadas por los 2 primeros digitos.
        rows = data.get('rows') or []
        first_row = row
        groups = []
        for item in rows:
            prefix = item['code'][:2]
            if not groups or groups[-1][0] != prefix:
                groups.append((prefix, []))
            groups[-1][1].append(item)
        for prefix, items in groups:
            group_row = row
            row += 1
            for item in items:
                ws.write_string(row, 0, item['code'], f['txt'])
                ws.write_string(row, 1, item['name'], f['txt'])
                write_formulas(row, item, f['num'])
                row += 1
            write_subtotal(group_row, group_row + 1, row - 1, prefix,
                           'Subtotal cuenta %s' % prefix, sums(items),
                           f['ws_group_lbl'], f['ws_group_num'])
        totals = sums(rows)
        if rows:
            write_subtotal(row, first_row, row - 1, 'TOTALES', '', totals,
                           f['total_lbl'], f['total_num'])
        else:
            ws.write(row, 0, 'TOTALES', f['total_lbl'])
        total_row = row
        row += 2

        # Control con el efectivo (cuenta 10).
        cash_rows = data.get('cash_rows') or []
        ws.merge_range(row, 0, row, len(cols) - 1,
                       'EFECTIVO Y EQUIVALENTES DE EFECTIVO (CUENTA 10) - CONTROL', f['section'])
        row += 1
        cash_first = row
        for item in cash_rows:
            ws.write_string(row, 0, item['code'], f['txt'])
            ws.write_string(row, 1, item['name'], f['txt'])
            ws.write_number(row, 2, item['final'], f['num'])
            ws.write_number(row, 3, item['initial'], f['num'])
            ws.write_formula(row, 4, '=%s-%s' % (cell(row, 3), cell(row, 2)),
                             f['num'], item['variation'])
            row += 1
        cash_variation = round(sum(i['variation'] for i in cash_rows), 2)
        ws.write(row, 0, 'TOTAL', f['total_lbl'])
        ws.write(row, 1, '', f['total_lbl'])
        for c in (2, 3, 4):
            key = cols[c][0]
            value = round(sum(i[key] for i in cash_rows), 2)
            if cash_rows:
                ws.write_formula(row, c, '=SUM(%s:%s)' % (cell(cash_first, c), cell(row - 1, c)),
                                 f['total_num'], value)
            else:
                ws.write_number(row, c, value, f['total_num'])
        cash_total_row = row
        row += 2

        net = float(self.data.get('net_change') or 0.0)
        fx = float(self.data.get('fx_effect') or 0.0)
        pl = data.get('pl_flow') or {}
        ws.merge_range(row, 0, row, len(cols) - 1,
                       'CONCILIACIÓN CON EL FORMATO 3.18', f['section'])
        row += 1
        r_bal, r_pl, r_sum, r_318, r_fx, r_cash, r_d318, r_dcash = range(row, row + 8)
        for r, text, fmt in (
            (r_bal, '(1) Flujo de las cuentas de balance (total de la tabla)', f['line_lbl']),
            (r_pl, '(2) Cobros y pagos registrados directamente contra cuentas de '
                   'resultados (ITF, diferencia de cambio, redondeos, ...)', f['line_lbl']),
            (r_sum, 'Flujo neto de las actividades = (1) + (2)', f['total_lbl']),
            (r_318, 'Flujo neto de las actividades según el formato 3.18', f['line_lbl']),
            (r_fx, 'Efecto de las variaciones en el tipo de cambio (formato 3.18)', f['line_lbl']),
            (r_cash, 'Aumento (disminución) del efectivo según contabilidad '
                     '(cuenta 10) = -(C)', f['line_lbl']),
            (r_d318, 'Diferencia con el formato 3.18 (debe ser cero)', f['total_lbl']),
            (r_dcash, 'Diferencia con el efectivo (debe ser cero)', f['total_lbl']),
        ):
            ws.merge_range(r, 0, r, 5, text, fmt)

        for c, key, total_key in ((6, 'flow', 'net_change'), (7, 'op', 'op_total'),
                                  (8, 'inv', 'inv_total'), (9, 'fin', 'fin_total')):
            bal_value = totals.get(key, 0.0)
            pl_value = float(pl.get(key) or 0.0)
            st_value = float(self.data.get(total_key) or 0.0)
            ws.write_formula(r_bal, c, '=%s' % cell(total_row, c), f['num'], bal_value)
            ws.write_number(r_pl, c, pl_value, f['num'])
            ws.write_formula(r_sum, c, '=%s+%s' % (cell(r_bal, c), cell(r_pl, c)),
                             f['total_num'], round(bal_value + pl_value, 2))
            ws.write_number(r_318, c, st_value, f['num'])
            ws.write_formula(r_d318, c, '=%s-%s' % (cell(r_sum, c), cell(r_318, c)),
                             f['ws_check_num'], round(bal_value + pl_value - st_value, 2))
        ws.write_number(r_fx, 6, fx, f['num'])
        ws.write_formula(r_cash, 6, '=-%s' % cell(cash_total_row, 4), f['num'], -cash_variation)
        ws.write_formula(r_dcash, 6, '=%s+%s-%s' % (cell(r_318, 6), cell(r_fx, 6), cell(r_cash, 6)),
                         f['ws_check_num'], round(net + fx + cash_variation, 2))
        return r_dcash + 1

    def _write_worksheet_lines(self, ws, row, data):
        """Detalle de cuentas de cada linea de cobros y pagos del estado."""
        f = self._formats
        lines = data.get('lines') or {}
        ws.merge_range(row, 0, row, 6,
                       'DETALLE POR LÍNEA DEL ESTADO DE FLUJOS DE EFECTIVO', f['section'])
        row += 1
        ws.set_row(row, 28)
        ws.merge_range(
            row, 0, row, 6,
            'Una misma cuenta puede aparecer en varias líneas: los cobros y los pagos se '
            'presentan por separado, y los préstamos y cuentas diversas con empresas del '
            'grupo (cuentas 14, 16, 17, 44, 46 y 47) se presentan en Inversión o '
            'Financiamiento; con terceros, en Operación.',
            f['ws_note'],
        )
        row += 1
        ws.set_row(row, 30)
        ws.write(row, 0, 'CUENTA', f['col'])
        ws.merge_range(row, 1, row, 5, 'DENOMINACIÓN', f['col'])
        ws.write(row, 6, 'IMPORTE', f['col'])
        row += 1

        section = None
        for kind, label, key in self.ROWS:
            if kind == 'section':
                section = label
                continue
            if kind != 'line' or not key or key not in lines:
                continue
            activity = self.ACTIVITY_SECTIONS.get(key.split('_')[0], '')
            if section and activity:
                ws.merge_range(row, 0, row, 6, activity, f['ws_group_lbl'])
                row += 1
                section = None
            first = row + 1
            detail = lines[key]
            ws.merge_range(row, 0, row, 5, label, f['total_lbl'])
            ws.write_formula(row, 6, '=SUM(G%d:G%d)' % (first + 1, first + len(detail)),
                             f['total_num'], round(sum(d['amount'] for d in detail), 2))
            row += 1
            for item in detail:
                ws.write_string(row, 0, item['code'], f['txt'])
                ws.merge_range(row, 1, row, 5, item['name'], f['txt'])
                ws.write_number(row, 6, item['amount'], f['num'])
                row += 1
        return row


# ===========================================================================
# 3.19 - Estado de cambios en el patrimonio neto
# ===========================================================================
class InvBal319ReportExcel(_PeriodHeaderMixin, InvBalReportBase):
    """Formato 3.19 - Estado de cambios en el patrimonio neto.

    `data`: {'columns': {clave: {'initial', 'final', 'rows': {'1'..'11':
    importe}}}, 'net_result'}
    """

    FORMATO_CODE = '3.19'
    FORMATO_TITLE = 'Estado de cambios en el patrimonio neto'
    SHEET_NAME = 'F3.19 Cambios Patrimonio'
    LANDSCAPE = True

    COLUMNS = [
        ('capital', 'CAPITAL'),
        ('capital_adic', 'CAPITAL ADICIONAL'),
        ('acciones_inv', 'ACCIONES DE INVERSIÓN'),
        ('exced_reval', 'EXCEDENTE DE REVALUACIÓN'),
        ('reserva_legal', 'RESERVA LEGAL'),
        ('otras_reservas', 'OTRAS RESERVAS'),
        ('res_acum', 'RESULTADOS ACUMULADOS'),
    ]
    ROWS = [
        ('1', '1. Efecto acumulado de los cambios en las políticas contables y la corrección de errores sustanciales'),
        ('2', '2. Distribuciones o asignaciones de utilidades efectuadas en el período'),
        ('3', '3. Dividendos y participaciones acordados durante el período'),
        ('4', '4. Nuevos aportes de accionistas'),
        ('5', '5. Movimiento de prima en la colocación de aportes y donaciones'),
        ('6', '6. Incrementos o disminuciones por fusiones o escisiones'),
        ('7', '7. Revaluación de activos'),
        ('8', '8. Capitalización de partidas patrimoniales'),
        ('9', '9. Redención de acciones de inversión o reducción de capital'),
        ('10', '10. Utilidad (pérdida) neta del ejercicio'),
        ('11', '11. Otros incrementos o disminuciones de las partidas patrimoniales'),
    ]

    def build(self, ws, workbook):
        f = self._formats
        f['concept'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter', 'border': 1, 'text_wrap': True,
        })
        n_cols = len(self.COLUMNS)
        total_col = n_cols + 1
        ws.set_column(0, 0, 52)
        ws.set_column(1, total_col, 15)

        row = self._write_period_header(ws, total_col)
        ws.set_row(row, 36)
        ws.write(row, 0, 'CONCEPTOS', f['col'])
        for col, (_key, label) in enumerate(self.COLUMNS, start=1):
            ws.write(row, col, label, f['col'])
        ws.write(row, total_col, 'TOTAL', f['col'])
        row += 1

        columns = self.data.get('columns') or {}

        def write_row(label, getter, label_fmt, num_fmt):
            ws.write(row, 0, label, label_fmt)
            total = 0.0
            for col, (key, _label) in enumerate(self.COLUMNS, start=1):
                value = getter(columns.get(key) or {})
                total += value
                ws.write_number(row, col, value, num_fmt)
            ws.write_number(row, total_col, total, num_fmt)

        start = self.obj.date_start.strftime('%d/%m/%Y') if self.obj.date_start else ''
        end = self.obj.date_end.strftime('%d/%m/%Y') if self.obj.date_end else ''

        write_row('SALDOS AL %s' % start, lambda c: float(c.get('initial') or 0.0),
                  f['total_lbl'], f['total_num'])
        row += 1
        for row_key, label in self.ROWS:
            write_row(label, lambda c, k=row_key: float((c.get('rows') or {}).get(k) or 0.0),
                      f['concept'], f['num'])
            row += 1
        write_row('SALDOS AL %s' % end, lambda c: float(c.get('final') or 0.0),
                  f['total_lbl'], f['total_num'])


# ===========================================================================
# 3.20 - Estado de resultados por funcion
# ===========================================================================
class InvBal320ReportExcel(_StatementReportBase):
    """Formato 3.20 - Estado de ganancias y perdidas por funcion.
    Ingresos en positivo y gastos en negativo."""

    FORMATO_CODE = '3.20'
    FORMATO_TITLE = 'Estado de ganancias y pérdidas por función'
    SHEET_NAME = 'F3.20 Resultados'

    ROWS = [
        ('line', 'Ventas Netas (ingresos operacionales)', 'ventas'),
        ('line', 'Descuentos, Rebajas y Bonificaciones Concedidos', None),
        ('line', 'Otros Ingresos Operacionales', 'otros_ing_op'),
        ('total', 'Total de Ingresos Brutos', 'total_ingresos'),
        ('blank', '', None),
        ('line', 'Costo de Ventas', 'costo_ventas'),
        ('total', 'Utilidad Bruta', 'utilidad_bruta'),
        ('blank', '', None),
        ('total', 'Gastos Operacionales', 'gastos_operacionales'),
        ('line', 'Gastos de Distribución', 'gastos_distribucion'),
        ('line', 'Gastos de Ventas', 'gastos_venta'),
        ('line', 'Gastos de Administración', 'gastos_adm'),
        ('total', 'Utilidad Operativa', 'utilidad_operativa'),
        ('blank', '', None),
        ('total', 'Otros Ingresos (Gastos)', 'otros_ing_gastos'),
        ('line', 'Ingresos Financieros', 'ingresos_fin'),
        ('line', 'Gastos Financieros', 'gastos_fin'),
        ('line', 'Diferencia de Cambio', 'dif_cambio'),
        ('line', 'Otros Ingresos', 'otros_ingresos'),
        ('line', 'Otros Gastos', 'otros_gastos'),
        ('line', 'Resultados por Exposición a la Inflación', None),
        ('total', 'Resultados antes de Participaciones, Impuesto a la Renta y Partidas Extraordinarias', 'antes_part'),
        ('blank', '', None),
        ('line', 'Participaciones', 'participaciones'),
        ('line', 'Impuesto a la Renta', 'impuesto_renta'),
        ('total', 'Resultados antes de Partidas Extraordinarias', 'antes_extra'),
        ('blank', '', None),
        ('line', 'Ingresos Extraordinarios', None),
        ('line', 'Gastos Extraordinarios', None),
        ('total', 'Resultado Antes de Interés Minoritario', 'antes_minoritario'),
        ('line', 'Interés Minoritario', None),
        ('total', 'Utilidad (Pérdida) Neta del Ejercicio', 'utilidad_neta'),
        ('blank', '', None),
        ('line', 'Dividendos de Acciones Preferentes', None),
        ('total', 'Utilidad (pérdida) Neta atribuible a los Accionistas', 'utilidad_atribuible'),
        ('line', 'Utilidad (pérdida) Básica por Acción Común', None),
        ('line', 'Utilidad (pérdida) Básica por Acción de Inversión', None),
        ('line', 'Utilidad (pérdida) Diluida por Acción Común', None),
        ('line', 'Utilidad (pérdida) Diluida por Acción de Inversión', None),
    ]