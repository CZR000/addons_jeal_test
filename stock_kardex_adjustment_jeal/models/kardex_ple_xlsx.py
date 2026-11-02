# -*- coding: utf-8 -*-
"""Libro físico de los formatos 13.1 y 12.1 en Excel (nota técnica 13.1/12.1,
puntos 3.2 y 4): una sección por existencia con su cabecera y columnas."""
from datetime import datetime, time

import xlsxwriter

from .kardex_engine import ROW_OPENING
from .kardex_ple import BOOK_121, BOOK_131, BOOK_TITLES, VALUATION_METHOD_NAME

ADJUSTMENT_COLOR = '#E2EFDA'
MANUAL_COLOR = '#DDEBF7'
TOTAL_COLOR = '#BFBFBF'


class _Formats:
    def __init__(self, workbook):
        self.workbook = workbook
        self._cache = {}
        self.title = workbook.add_format({'bold': True, 'font_size': 11})
        self.label = workbook.add_format({'bold': True, 'font_size': 9})
        self.value = workbook.add_format({'font_size': 9})
        self.header = workbook.add_format({
            'bold': True, 'font_size': 8, 'border': 1, 'align': 'center',
            'valign': 'vcenter', 'text_wrap': True})
        self.note = workbook.add_format({'font_size': 8, 'italic': True})

    def get(self, kind, color=None, bold=False):
        key = (kind, color, bold)
        if key not in self._cache:
            props = {'font_size': 8, 'border': 1}
            if color:
                props['bg_color'] = color
            if bold:
                props['bold'] = True
            if kind == 'qty':
                props['num_format'] = '#,##0.00##;-#,##0.00##;0.00'
            elif kind == 'money':
                props['num_format'] = '#,##0.00;-#,##0.00;0.00'
            elif kind == 'unit':
                props['num_format'] = '#,##0.0000;-#,##0.0000;0.00'
            elif kind == 'date':
                props['num_format'] = 'dd/mm/yyyy'
                props['align'] = 'center'
            elif kind == 'center':
                props['align'] = 'center'
            self._cache[key] = self.workbook.add_format(props)
        return self._cache[key]


def _write_company_header(sheet, fmt, process, book, row):
    company = process.company_id
    sheet.write(row, 0, BOOK_TITLES[book], fmt.title)
    row += 2
    for label, value in (
        ('PERÍODO:', process.date_from.strftime('%m/%Y')),
        ('RUC:', company.vat or ''),
        ('APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL:', company.name or ''),
    ):
        sheet.write(row, 0, label, fmt.label)
        sheet.write(row, 5, value, fmt.value)
        row += 1
    return row


def _write_section_header(sheet, fmt, section, book, row):
    items = [
        ('ESTABLECIMIENTO (1):', section['establishment']),
        ('CÓDIGO DE LA EXISTENCIA:', section['code']),
        ('TIPO (TABLA 5):', section['stock_type']),
        ('DESCRIPCIÓN:', section['description']),
        ('CÓDIGO DE LA UNIDAD DE MEDIDA (TABLA 6):', section['uom']),
    ]
    if book == BOOK_131:
        items.append(('MÉTODO DE VALUACIÓN:', VALUATION_METHOD_NAME))
    for label, value in items:
        sheet.write(row, 0, label, fmt.label)
        sheet.write(row, 5, value, fmt.value)
        row += 1
    return row + 1


def _write_table_header(sheet, fmt, book, row):
    h = fmt.header
    sheet.merge_range(row, 0, row + 1, 3,
                      'DOCUMENTO DE TRASLADO, COMPROBANTE DE PAGO,\nDOCUMENTO INTERNO O SIMILAR', h)
    sheet.merge_range(row, 4, row + 2, 4, 'TIPO DE\nOPERACIÓN\n(TABLA 12)', h)
    for col, label in enumerate(('FECHA', 'TIPO (TABLA 10)', 'SERIE', 'NÚMERO')):
        sheet.write(row + 2, col, label, h)
    if book == BOOK_131:
        for start, label in ((5, 'ENTRADAS'), (8, 'SALIDAS'), (11, 'SALDO FINAL')):
            sheet.merge_range(row, start, row, start + 2, label, h)
            for offset, sub in enumerate(('CANTIDAD', 'COSTO UNITARIO', 'COSTO TOTAL')):
                sheet.merge_range(row + 1, start + offset, row + 2, start + offset, sub, h)
        sheet.merge_range(row, 14, row + 2, 14, 'OBSERVACIÓN', h)
    else:
        for col, label in ((5, 'ENTRADAS'), (6, 'SALIDAS'), (7, 'SALDO FINAL')):
            sheet.merge_range(row, col, row + 2, col, label, h)
        sheet.merge_range(row, 8, row + 2, 8, 'OBSERVACIÓN', h)
    return row + 3


def _line_color(line):
    if line['is_adjustment']:
        return ADJUSTMENT_COLOR
    if line['kind'] == 'manual':
        return MANUAL_COLOR
    return None


def _write_line(sheet, fmt, book, line, row):
    color = _line_color(line)
    opening = line['kind'] == ROW_OPENING
    if opening:
        sheet.write(row, 0, '', fmt.get('text', color))
        sheet.write(row, 1, '', fmt.get('text', color))
        sheet.write(row, 2, '', fmt.get('text', color))
        sheet.write(row, 3, 'SALDO INICIAL', fmt.get('center', color))
    else:
        sheet.write_datetime(row, 0, _as_datetime(line['doc_date']), fmt.get('date', color))
        sheet.write(row, 1, line['doc_type'], fmt.get('center', color))
        sheet.write(row, 2, line['serie'], fmt.get('center', color))
        sheet.write(row, 3, line['number'], fmt.get('center', color))
    sheet.write(row, 4, line['operation'], fmt.get('center', color))
    note = line['note'] or ''
    if line['is_adjustment'] or line['kind'] == 'manual':
        note = ' '.join(filter(None, [line.get('move_name', ''), note]))
    elif line.get('reference'):
        note = ' '.join(filter(None, [line['reference'], note]))
    if book == BOOK_131:
        values = [
            (line['in_qty'], 'qty'), (line['in_unit'], 'unit'), (line['in_total'], 'money'),
            (line['out_qty'], 'qty'), (line['out_unit'], 'unit'), (line['out_total'], 'money'),
            (line['bal_qty'], 'qty'), (line['bal_unit'], 'unit'), (line['bal_total'], 'money'),
        ]
        for offset, (value, kind) in enumerate(values):
            sheet.write_number(row, 5 + offset, value or 0.0, fmt.get(kind, color))
        sheet.write(row, 14, note, fmt.get('text', color))
    else:
        sheet.write_number(row, 5, 0.0 if opening else line['in_qty'], fmt.get('qty', color))
        sheet.write_number(row, 6, 0.0 if opening else line['out_qty'], fmt.get('qty', color))
        sheet.write_number(row, 7, line['bal_qty'], fmt.get('qty', color))
        sheet.write(row, 8, note, fmt.get('text', color))
    return row + 1


def _write_totals(sheet, fmt, book, section, row):
    totals = section['totals']
    grey = fmt.get('money', TOTAL_COLOR)
    sheet.merge_range(row, 0, row, 4, 'TOTALES', fmt.get('center', None, bold=True))
    if book == BOOK_131:
        sheet.write_number(row, 5, totals.get('in_qty', 0.0), fmt.get('qty', bold=True))
        sheet.write(row, 6, '', grey)
        sheet.write_number(row, 7, totals.get('in_total', 0.0), fmt.get('money', bold=True))
        sheet.write_number(row, 8, totals.get('out_qty', 0.0), fmt.get('qty', bold=True))
        sheet.write(row, 9, '', grey)
        sheet.write_number(row, 10, totals.get('out_total', 0.0), fmt.get('money', bold=True))
        for col in (11, 12, 13):
            sheet.write(row, col, '', grey)
    else:
        sheet.write_number(row, 5, totals.get('in_qty', 0.0), fmt.get('qty', bold=True))
        sheet.write_number(row, 6, totals.get('out_qty', 0.0), fmt.get('qty', bold=True))
        sheet.write(row, 7, '', grey)
    return row + 1


def _as_datetime(value):
    return datetime.combine(value, time.min)


def build_ple_workbook(process, book, sections, output):
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    fmt = _Formats(workbook)
    sheet = workbook.add_worksheet('13.1' if book == BOOK_131 else '12.1')
    sheet.set_landscape()
    sheet.set_paper(9)
    sheet.fit_to_pages(1, 0)
    sheet.set_margins(0.3, 0.3, 0.4, 0.4)
    widths = [11, 8, 8, 12, 9] + ([11, 12, 14] * 3 + [45] if book == BOOK_131 else [13, 13, 13, 45])
    for col, width in enumerate(widths):
        sheet.set_column(col, col, width)
    row = _write_company_header(sheet, fmt, process, book, 0) + 1
    if not sections:
        sheet.write(row, 0, 'Sin existencias en el período.', fmt.label)
    for section in sections:
        row = _write_section_header(sheet, fmt, section, book, row)
        row = _write_table_header(sheet, fmt, book, row)
        for line in section['lines']:
            row = _write_line(sheet, fmt, book, line, row)
        row = _write_totals(sheet, fmt, book, section, row)
        row += 2
    sheet.write(row, 0, '(1) Dirección del Establecimiento o Código según el Registro Único '
                        'de Contribuyentes.', fmt.note)
    if book == BOOK_131:
        sheet.write(row + 1, 0, 'Filas sombreadas en verde: ajustes del kardex (cantidad 0, '
                                'importe en costo total). En celeste: asientos manuales incluidos.',
                    fmt.note)
    workbook.close()
