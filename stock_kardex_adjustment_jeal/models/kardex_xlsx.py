# -*- coding: utf-8 -*-
"""Exportación del kardex con ajustes a Excel (nota técnica, punto 7)."""
from collections import defaultdict
from datetime import datetime, time

import pytz
import xlsxwriter

from odoo.tools import format_date

COLORS = {
    'opening': '#D9E1F2',
    'manual': '#DDEBF7',
    'adj_cost': '#E2EFDA',
    'adj_fx': '#E4DFEC',
    'adj_price': '#FCE4D6',
    'adj_prod': '#FFF2CC',
    'total': '#FFF2CC',
}

ROW_LABELS = {
    'adj_cost': '99 - Ajuste de costo',
    'adj_fx': '99 - Ajuste diferencia de cambio (factura vs recepción)',
    'adj_price': '99 - Ajuste diferencia de precio (factura vs recepción)',
    'adj_prod': '99 - Ajuste de fabricación o desmontaje',
}

KARDEX_HEADERS = [
    ('Código', 12), ('Producto', 38), ('Cuenta', 10), ('Fecha contable', 12),
    ('Asiento', 20), ('Ref. almacén', 18), ('Tipo operación (Tabla 12)', 10),
    ('Tipo doc.', 7), ('Serie-Número', 20), ('Proveedor/Cliente', 30),
    ('Entrada Cant.', 12), ('Entrada C.U.', 12), ('Entrada Costo', 15),
    ('Salida Cant.', 12), ('Salida C.U.', 12), ('Salida Costo', 15),
    ('Saldo Cant.', 12), ('Saldo C.U.', 12), ('Saldo Costo', 15),
    ('Costo recalculado (último promedio)', 15), ('Ajuste (+ entrada / - salida)', 14),
    ('Fecha creación en Odoo', 17), ('Observación', 45),
    ('TC factura', 10), ('TC recepción', 10),
]

ODOO_HEADERS = [
    ('Código', 12), ('Producto', 38), ('Cuenta', 10), ('Fecha contable', 12),
    ('Asiento', 20), ('Ref. almacén', 18), ('Entrada Cant.', 12), ('Entrada Costo', 15),
    ('Salida Cant.', 12), ('Salida Costo', 15), ('Saldo Cant.', 12), ('Saldo C.U.', 12),
    ('Saldo Costo', 15),
]


class _Formats:
    def __init__(self, workbook):
        base = {'font_size': 9, 'border': 1, 'border_color': '#BFBFBF'}
        self.workbook = workbook
        self._cache = {}
        self.base = base
        self.title = workbook.add_format({'bold': True, 'font_size': 13})
        self.subtitle = workbook.add_format({'italic': True, 'font_size': 9})
        self.header = workbook.add_format(dict(
            base, bold=True, bg_color='#1F4E78', font_color='#FFFFFF',
            text_wrap=True, align='center', valign='vcenter'))

    def get(self, kind, color=None, bold=False):
        key = (kind, color, bold)
        if key not in self._cache:
            props = dict(self.base)
            if color:
                props['bg_color'] = color
            if bold:
                props['bold'] = True
            if kind == 'qty':
                props['num_format'] = '#,##0.00;-#,##0.00;""'
            elif kind == 'money':
                props['num_format'] = '#,##0.00;-#,##0.00;""'
            elif kind == 'money0':
                props['num_format'] = '#,##0.00;-#,##0.00;0.00'
            elif kind == 'unit':
                props['num_format'] = '#,##0.0000;-#,##0.0000;""'
            elif kind == 'rate':
                props['num_format'] = '0.000;-0.000;""'
            elif kind == 'date':
                props['num_format'] = 'dd/mm/yyyy'
            elif kind == 'datetime':
                props['num_format'] = 'dd/mm/yyyy hh:mm'
            self._cache[key] = self.workbook.add_format(props)
        return self._cache[key]


def _write_headers(sheet, fmt, row, headers):
    for col, (label, width) in enumerate(headers):
        sheet.write(row, col, label, fmt.header)
        sheet.set_column(col, col, width)
    sheet.set_row(row, 36)
    sheet.freeze_panes(row + 1, 2)


def _title(sheet, fmt, run, title):
    sheet.write(0, 0, title, fmt.title)
    sheet.write(1, 0, '%s · %s al %s · base: fecha contable' % (
        run.company_id.name, format_date(run.env, run.date_from),
        format_date(run.env, run.date_to)), fmt.subtitle)


def _local_dt(value, tz):
    if not value:
        return None
    return pytz.UTC.localize(value).astimezone(tz).replace(tzinfo=None)


def build_workbook(run, output):
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    fmt = _Formats(workbook)
    tz = run._user_tz()
    rows_by_product = defaultdict(list)
    for row in run.row_ids:
        rows_by_product[row.product_id.id].append(row)
    summaries = run.summary_ids
    _write_kardex(workbook, fmt, run, summaries, rows_by_product, tz)
    _write_summary(workbook, fmt, run, summaries)
    _write_reconciliation(workbook, fmt, run, summaries)
    _write_odoo_kardex(workbook, fmt, run, summaries, rows_by_product)
    workbook.close()


def _write_kardex(workbook, fmt, run, summaries, rows_by_product, tz):
    sheet = workbook.add_worksheet('Kardex')
    _title(sheet, fmt, run, 'Kardex valorizado con ajustes al costo promedio y por tipo de cambio')
    r = 3
    _write_headers(sheet, fmt, r, KARDEX_HEADERS)
    r += 1
    for summary in summaries:
        product = summary.product_id
        code = product.default_code or ''
        name = product.with_context(display_default_code=False).display_name
        account = summary.account_id.code or ''
        for row in rows_by_product.get(product.id, []):
            color = COLORS.get(row.row_type)
            t = lambda kind: fmt.get(kind, color)  # noqa: E731
            if row.row_type == 'opening':
                values = [code, name, account, row.date, '', '', '', '', '', 'Saldo inicial']
            else:
                label = row.reference
                operation = row.operation_type
                if row.row_type in ROW_LABELS:
                    label = '%s %s' % (ROW_LABELS[row.row_type], row.reference or '')
                values = [code, name, account, row.date, row.account_move_id.name or '',
                          label, operation, row.doc_type, row.doc_number, row.partner]
            for col, value in enumerate(values):
                if col == 3:
                    sheet.write_datetime(r, col, _as_datetime(value), t('date'))
                else:
                    sheet.write(r, col, value or '', t('text'))
            nums = [
                (row.in_qty, 'qty'), (row.in_unit, 'unit'), (row.in_value, 'money'),
                (row.out_qty, 'qty'), (row.out_unit, 'unit'), (row.out_value, 'money'),
                (row.bal_qty, 'qty'), (row.bal_unit, 'unit'), (row.bal_value, 'money0'),
                (row.recalc_value, 'money'), (row.adjust_value, 'money'),
            ]
            for offset, (value, kind) in enumerate(nums):
                sheet.write_number(r, 10 + offset, value or 0.0, t(kind))
            created = _local_dt(row.odoo_create_date, tz)
            if created:
                sheet.write_datetime(r, 21, created, t('datetime'))
            else:
                sheet.write(r, 21, '', t('text'))
            sheet.write(r, 22, row.note or '', t('text'))
            sheet.write_number(r, 23, row.tc_invoice or 0.0, t('rate'))
            sheet.write_number(r, 24, row.tc_receipt or 0.0, t('rate'))
            r += 1
        # Total del producto
        color = COLORS['total']
        sheet.write(r, 0, code, fmt.get('text', color, True))
        sheet.write(r, 1, 'Total %s' % name, fmt.get('text', color, True))
        for col in range(2, 10):
            sheet.write(r, col, '', fmt.get('text', color, True))
        totals = [
            (summary.in_qty, 'qty'), (0.0, 'unit'),
            (_sum(rows_by_product[product.id], 'in_value', exclude_opening=True), 'money'),
            (summary.out_qty, 'qty'), (0.0, 'unit'),
            (_sum(rows_by_product[product.id], 'out_value', exclude_opening=True), 'money'),
            (summary.closing_qty, 'qty'), (summary.closing_unit, 'unit'),
            (summary.closing_value, 'money0'),
            (summary.out_recalc_value, 'money'),
            (summary.cost_adjust + summary.return_adjust + summary.fx_adjust
             + summary.price_adjust + summary.production_adjust, 'money'),
        ]
        for offset, (value, kind) in enumerate(totals):
            sheet.write_number(r, 10 + offset, value or 0.0, fmt.get(kind, color, True))
        for col in range(21, 25):
            sheet.write(r, col, '', fmt.get('text', color, True))
        r += 2
    sheet.autofilter(3, 0, max(r - 1, 4), len(KARDEX_HEADERS) - 1)


def _sum(rows, field, exclude_opening=False):
    return sum(getattr(row, field) for row in rows
               if not (exclude_opening and row.row_type == 'opening'))


def _as_datetime(value):
    return datetime.combine(value, time.min)


def _write_summary(workbook, fmt, run, summaries):
    sheet = workbook.add_worksheet('Resumen por producto')
    _title(sheet, fmt, run, 'Resumen por producto')
    headers = [
        ('Código', 12), ('Producto', 38), ('Cuenta', 10),
        ('Saldo inicial cant.', 13), ('Saldo inicial', 15),
        ('Entradas cant.', 13), ('Entradas', 15),
        ('Salidas cant.', 13), ('Salidas según Odoo', 15), ('Salidas recalculadas', 15),
        ('Ajustes de costo promedio', 14), ('Ajustes de devoluciones', 14),
        ('Ajustes de cambio', 14), ('Ajustes de precio', 14), ('Ajustes de fabricación', 14),
        ('Manuales', 14),
        ('Saldo final cant.', 13), ('Saldo final', 15), ('C.U. final', 13),
        ('Saldo final a costo Odoo', 15),
    ]
    r = 3
    _write_headers(sheet, fmt, r, headers)
    r += 1
    totals = defaultdict(float)
    for s in summaries:
        values = [
            (s.opening_qty, 'qty'), (s.opening_value, 'money0'),
            (s.in_qty, 'qty'), (s.in_value, 'money'),
            (s.out_qty, 'qty'), (s.out_value, 'money'), (s.out_recalc_value, 'money'),
            (s.cost_adjust, 'money'), (s.return_adjust, 'money'), (s.fx_adjust, 'money'),
            (s.price_adjust, 'money'), (s.production_adjust, 'money'), (s.manual_value, 'money'),
            (s.closing_qty, 'qty'), (s.closing_value, 'money0'), (s.closing_unit, 'unit'),
            (s.raw_closing_value, 'money0'),
        ]
        sheet.write(r, 0, s.product_id.default_code or '', fmt.get('text'))
        sheet.write(r, 1, s.product_id.with_context(display_default_code=False).display_name, fmt.get('text'))
        sheet.write(r, 2, s.account_id.code or '', fmt.get('text'))
        for offset, (value, kind) in enumerate(values):
            sheet.write_number(r, 3 + offset, value or 0.0, fmt.get(kind))
            if kind != 'unit':
                totals[offset] += value or 0.0
        r += 1
    color = COLORS['total']
    sheet.write(r, 0, '', fmt.get('text', color, True))
    sheet.write(r, 1, 'Total', fmt.get('text', color, True))
    sheet.write(r, 2, '', fmt.get('text', color, True))
    unit_col = len(headers) - 5
    for offset in range(len(headers) - 3):
        kind = 'unit' if offset == unit_col else 'money0'
        sheet.write_number(r, 3 + offset, totals.get(offset, 0.0) if offset != unit_col else 0.0,
                           fmt.get(kind, color, True))


def _write_reconciliation(workbook, fmt, run, summaries):
    sheet = workbook.add_worksheet('Conciliación 20-24')
    _title(sheet, fmt, run, 'Conciliación del kardex contra las cuentas de valoración')
    headers = [
        ('Cuenta', 10), ('Código', 12), ('Producto', 38), ('Saldo kardex', 16),
        ('Saldo contable', 16), ('Diferencia', 14),
    ]
    r = 3
    _write_headers(sheet, fmt, r, headers)
    r += 1
    balances = run._accounting_balances()
    seen = set()
    by_account = defaultdict(lambda: [0.0, 0.0])
    for s in summaries.sorted(lambda s: (s.account_id.code or '', s.product_id.default_code or '')):
        key = (s.account_id.id, s.product_id.id)
        seen.add(key)
        accounting = balances.get(key, 0.0)
        _reco_row(sheet, fmt, r, s.account_id.code, s.product_id, s.closing_value, accounting)
        by_account[s.account_id.code][0] += s.closing_value
        by_account[s.account_id.code][1] += accounting
        r += 1
    # Apuntes de las cuentas de valoración sin producto o de productos sin kardex
    accounts = {a.id: a for a in summaries.account_id}
    products = run.env['product.product']
    for (account_id, product_id), balance in sorted(balances.items(), key=lambda i: (accounts[i[0][0]].code, i[0][1] or 0)):
        if (account_id, product_id) in seen or run.company_id.currency_id.is_zero(balance):
            continue
        product = products.browse(product_id) if product_id else products
        _reco_row(sheet, fmt, r, accounts[account_id].code, product, 0.0, balance,
                  note='Sin kardex' if product else 'Apuntes sin producto')
        by_account[accounts[account_id].code][1] += balance
        r += 1
    r += 1
    color = COLORS['total']
    for code, (kardex, accounting) in sorted(by_account.items()):
        sheet.write(r, 0, code, fmt.get('text', color, True))
        sheet.write(r, 1, '', fmt.get('text', color, True))
        sheet.write(r, 2, 'Total cuenta', fmt.get('text', color, True))
        sheet.write_number(r, 3, kardex, fmt.get('money0', color, True))
        sheet.write_number(r, 4, accounting, fmt.get('money0', color, True))
        sheet.write_number(r, 5, kardex - accounting, fmt.get('money0', color, True))
        r += 1


def _reco_row(sheet, fmt, r, code, product, kardex, accounting, note=None):
    sheet.write(r, 0, code or '', fmt.get('text'))
    sheet.write(r, 1, product.default_code or '' if product else '', fmt.get('text'))
    name = product.with_context(display_default_code=False).display_name if product else ''
    sheet.write(r, 2, '%s%s' % (name, (' (%s)' % note) if note else ''), fmt.get('text'))
    sheet.write_number(r, 3, kardex, fmt.get('money0'))
    sheet.write_number(r, 4, accounting, fmt.get('money0'))
    sheet.write_number(r, 5, kardex - accounting, fmt.get('money0'))


def _write_odoo_kardex(workbook, fmt, run, summaries, rows_by_product):
    """Kardex a los costos registrados por Odoo, sin ajustes."""
    sheet = workbook.add_worksheet('Kardex costos Odoo')
    _title(sheet, fmt, run, 'Kardex a costos de Odoo (sin ajustes), para comparación')
    r = 3
    _write_headers(sheet, fmt, r, ODOO_HEADERS)
    r += 1
    for summary in summaries:
        product = summary.product_id
        code = product.default_code or ''
        name = product.with_context(display_default_code=False).display_name
        account = summary.account_id.code or ''
        for row in rows_by_product.get(product.id, []):
            if row.row_type in ROW_LABELS:
                continue
            color = COLORS.get(row.row_type)
            label = 'Saldo inicial' if row.row_type == 'opening' else row.reference
            sheet.write(r, 0, code, fmt.get('text', color))
            sheet.write(r, 1, name, fmt.get('text', color))
            sheet.write(r, 2, account, fmt.get('text', color))
            sheet.write_datetime(r, 3, _as_datetime(row.date), fmt.get('date', color))
            sheet.write(r, 4, row.account_move_id.name or '', fmt.get('text', color))
            sheet.write(r, 5, label or '', fmt.get('text', color))
            unit = row.raw_bal_value / row.bal_qty if row.bal_qty else 0.0
            nums = [
                (row.in_qty, 'qty'), (row.in_value, 'money'),
                (row.out_qty, 'qty'), (row.out_value, 'money'),
                (row.bal_qty, 'qty'), (unit, 'unit'), (row.raw_bal_value, 'money0'),
            ]
            for offset, (value, kind) in enumerate(nums):
                sheet.write_number(r, 6 + offset, value or 0.0, fmt.get(kind, color))
            r += 1
        color = COLORS['total']
        sheet.write(r, 0, code, fmt.get('text', color, True))
        sheet.write(r, 1, 'Total %s' % name, fmt.get('text', color, True))
        for col in range(2, 10):
            sheet.write(r, col, '', fmt.get('text', color, True))
        sheet.write_number(r, 10, summary.closing_qty, fmt.get('qty', color, True))
        unit = summary.raw_closing_value / summary.closing_qty if summary.closing_qty else 0.0
        sheet.write_number(r, 11, unit, fmt.get('unit', color, True))
        sheet.write_number(r, 12, summary.raw_closing_value, fmt.get('money0', color, True))
        r += 2
