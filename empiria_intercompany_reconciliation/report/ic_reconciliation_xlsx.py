"""Libro Excel de una ejecución de la conciliación intercompany (sección 7 del
diseño funcional): Notas, Resumen, Por categoría, Detalle, Emparejamientos
manuales y Reglas."""
import base64
import io

import xlsxwriter

from ..engine import CATEGORIES, CATEGORY_HINTS
from ..engine import LOAN_PREFIXES
from ..models.ic_reconciliation_line import RULES

DETAIL_COLUMNS = [
    ('Par', 34), ('Bloque', 40), ('Categoría', 34), ('Regla', 8), ('Registrado en', 26), ('Contraparte', 26),
    ('Tipo', 14), ('Asiento', 22), ('Comprobante', 16), ('Fecha', 11), ('Cuenta', 10), ('Moneda', 8),
    ('Importe moneda', 16), ('Importe S/', 16), ('Documento en la contraparte', 24), ('Fecha contraparte', 12),
    ('Importe contraparte', 16), ('Importe contraparte S/', 16), ('Efecto en la diferencia', 18),
    ('Glosa', 40), ('Observación', 50), ('Qué hacer', 50), ('Estado', 12), ('Nuevo', 7),
    ('Revisado por', 18), ('Fecha revisión', 16), ('Comentario', 40), ('Cuenta distinta', 40),
    ('Posible contraparte', 50),
]


def build_workbook(run):
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
    base = {'font_name': 'Arial', 'font_size': 9}
    fmt = {
        'title': workbook.add_format({**base, 'bold': True, 'font_size': 13}),
        'head': workbook.add_format({**base, 'bold': True, 'bg_color': '#2D1E2F', 'font_color': '#FFFFFF',
                                     'text_wrap': True, 'valign': 'top', 'border': 1}),
        'text': workbook.add_format(base),
        'wrap': workbook.add_format({**base, 'text_wrap': True, 'valign': 'top'}),
        'bold': workbook.add_format({**base, 'bold': True}),
        'money': workbook.add_format({**base, 'num_format': '#,##0.00;[Red]-#,##0.00'}),
        'money_bold': workbook.add_format({**base, 'bold': True, 'num_format': '#,##0.00;[Red]-#,##0.00'}),
        'date': workbook.add_format({**base, 'num_format': 'dd/mm/yyyy'}),
        'warn': workbook.add_format({**base, 'bold': True, 'font_color': '#B00020'}),
    }
    lines = run.line_ids.sudo()
    pairs = run.pair_ids.sudo()
    block_labels = {pair.id: pair.block_name for pair in pairs}
    pair_name = {pair.id: f"{pair.company_a_id.name} ↔ {pair.company_b_id.name}" for pair in pairs}
    category_label = {key: label for key, label, _hint in CATEGORIES}
    rule_label = dict(RULES)

    # Hojas en el orden del diseño funcional.
    sheet = workbook.add_worksheet('Notas')
    summary = workbook.add_worksheet('Resumen')
    by_category = workbook.add_worksheet('Por categoría')

    # Notas -------------------------------------------------------------- #
    sheet.set_column(0, 0, 32)
    sheet.set_column(1, 1, 110)
    config = run.env['ic.reconciliation.config'].get_config()
    notes = [
        ('Base', run.env.cr.dbname),
        ('Ejecución', run.name),
        ('Periodo', f"del {run.date_from:%d/%m/%Y} al {run.date_to:%d/%m/%Y}" if run.date_from
         else f"acumulado al {run.date_to:%d/%m/%Y}"),
        ('Fecha de corte', run.date_to.strftime('%d/%m/%Y')),
        ('Origen', dict(run._fields['origin'].selection).get(run.origin)),
        ('Generado por / el', f"{run.user_id.name} · {run.create_date:%d/%m/%Y %H:%M}"),
        ('Empresas', ', '.join((run.company_ids or config._get_companies()).mapped('name'))),
        ('Bloques', f"por quién cobra: cuentas por cobrar {config.receivable_prefixes} de una empresa contra "
                    f"cuentas por pagar {config.payable_prefixes} de la otra"),
        ('Cuenta distinta', f"si una empresa usa la familia préstamos ({', '.join(LOAN_PREFIXES)}) y la otra no, la línea "
                            f"se concilia con la observación automática (columna Cuenta distinta)"),
        ('Pares por conciliar / líneas pendientes', f"{run.pending_pair_count} / {run.pending_line_count}"),
        ('Control', 'Correcto: diferencia − suma de categorías = 0 en todos los pares' if run.control_ok
         else f'NO DEFINITIVA: el control no es 0 en algún par (total {run.control_total:,.2f})'),
        ('Cómo leerlo', 'Cada fila del Resumen es un par de empresas en un bloque. Saldo A con B + saldo B con A '
                        'debería ser 0; la diferencia se explica por categoría (fórmulas SUMIFS sobre el Detalle) y '
                        'el control debe ser 0. El Detalle dice dónde está registrado cada documento o movimiento, '
                        'qué tiene la otra empresa y qué hacer. Importes en soles salvo "Importe moneda".'),
        ('Periodo y saldos', 'Los saldos son siempre los acumulados a la fecha de corte. Con periodo, el Detalle '
                             'muestra lo que pasó en el periodo y todo apunte anterior a la fecha desde va a '
                             '"Arrastre anterior al periodo" (una línea por par), que es igual a la "Diferencia al '
                             'inicio": diferencia al inicio + movimientos del periodo = diferencia final.'),
        ('Qué no hace', 'No crea, modifica ni concilia asientos. Lo que corrige el saldo es el documento que se '
                        'registra o corrige en la empresa que corresponde.'),
    ]
    sheet.write(0, 0, 'Conciliación intercompany por documento', fmt['title'])
    for row, (key, value) in enumerate(notes, start=2):
        sheet.write(row, 0, key, fmt['bold'])
        sheet.write(row, 1, value, fmt['warn'] if key == 'Control' and not run.control_ok else fmt['wrap'])

    # Detalle (primero, para las fórmulas del Resumen) ------------------- #
    detail = workbook.add_worksheet('Detalle')
    for col, (title, width) in enumerate(DETAIL_COLUMNS):
        detail.write(0, col, title, fmt['head'])
        detail.set_column(col, col, width)
    status_label = dict(lines._fields['status'].selection)
    doc_label = dict(lines._fields['doc_type'].selection)
    for row, line in enumerate(lines.sorted(lambda l: (l.pair_id.id, l.category, -abs(l.effect_pen))), start=1):
        values = [
            pair_name[line.pair_id.id], block_labels.get(line.pair_id.id), category_label.get(line.category), line.rule,
            line.company_id.name, line.counterpart_company_id.name, doc_label.get(line.doc_type, ''),
            line.move_name or '', line.doc_number or '', line.date, line.account_code or '',
            line.line_currency_id.name or '', line.amount_currency, line.amount_pen,
            line.counterpart_move_name or '', line.counterpart_date, line.counterpart_amount_currency,
            line.counterpart_amount_pen, line.effect_pen, line.label or '', line.note or '', line.action_hint or '',
            status_label.get(line.status), 'Sí' if line.is_new else '', line.review_user_id.name or '',
            line.review_date, line.review_comment or '', line.account_note or '', line.suggestion_note or '',
        ]
        for col, value in enumerate(values):
            if col in (9, 15, 25):
                if value:
                    detail.write_datetime(row, col, value if hasattr(value, 'hour') else _to_datetime(value), fmt['date'])
            elif col in (12, 13, 16, 17, 18):
                detail.write_number(row, col, value or 0.0, fmt['money'])
            else:
                detail.write(row, col, value, fmt['text'])
    last_detail = max(len(lines), 1)
    detail.freeze_panes(1, 0)
    detail.autofilter(0, 0, last_detail, len(DETAIL_COLUMNS) - 1)

    # Resumen ------------------------------------------------------------ #
    categories = [(key, label) for key, label, _hint in CATEGORIES]
    head = ['Bloque', 'Empresa A', 'Empresa B', 'Saldo A con B', 'Saldo B con A', 'Diferencia', 'Estado',
            'Pendientes', 'Revisados'] + [label for _key, label in categories] + ['Control', 'Total del par']
    if run.date_from:
        head += ['Saldo inicial A con B', 'Saldo inicial B con A', 'Diferencia al inicio']
    for col, title in enumerate(head):
        summary.write(0, col, title, fmt['head'])
    summary.set_column(0, 0, 40)
    summary.set_column(1, 2, 26)
    summary.set_column(3, len(head), 15)
    state_label = dict(pairs._fields['state'].selection)
    first_category_col = 9
    for row, pair in enumerate(pairs, start=1):
        excel_row = row + 1
        summary.write(row, 0, block_labels.get(pair.id), fmt['text'])
        summary.write(row, 1, pair.company_a_id.name, fmt['text'])
        summary.write(row, 2, pair.company_b_id.name, fmt['text'])
        summary.write_number(row, 3, pair.balance_a, fmt['money'])
        summary.write_number(row, 4, pair.balance_b, fmt['money'])
        summary.write_formula(row, 5, f'=D{excel_row}+E{excel_row}', fmt['money_bold'], pair.difference)
        summary.write(row, 6, state_label.get(pair.state), fmt['text'])
        summary.write_number(row, 7, pair.pending_count, fmt['text'])
        summary.write_number(row, 8, pair.reviewed_count, fmt['text'])
        name = pair_name[pair.id].replace('"', '""')
        block = (block_labels.get(pair.id) or '').replace('"', '""')
        for index, (key, label) in enumerate(categories):
            col = first_category_col + index
            formula = (f'=SUMIFS(Detalle!$S$2:$S${last_detail + 1},Detalle!$A$2:$A${last_detail + 1},"{name}",'
                       f'Detalle!$B$2:$B${last_detail + 1},"{block}",Detalle!$C$2:$C${last_detail + 1},"{label}")')
            summary.write_formula(row, col, formula, fmt['money'], pair[f'amount_{key}'])
        control_col = first_category_col + len(categories)
        first = xlsxwriter.utility.xl_col_to_name(first_category_col)
        last = xlsxwriter.utility.xl_col_to_name(control_col - 1)
        summary.write_formula(row, control_col, f'=F{excel_row}-SUM({first}{excel_row}:{last}{excel_row})',
                              fmt['money_bold'], pair.control)
        summary.write_number(row, control_col + 1, pair.total_difference, fmt['money'])
        if run.date_from:
            summary.write_number(row, control_col + 2, pair.opening_a, fmt['money'])
            summary.write_number(row, control_col + 3, pair.opening_b, fmt['money'])
            opening_a = xlsxwriter.utility.xl_col_to_name(control_col + 2)
            opening_b = xlsxwriter.utility.xl_col_to_name(control_col + 3)
            summary.write_formula(row, control_col + 4, f'={opening_a}{excel_row}+{opening_b}{excel_row}',
                                  fmt['money'], pair.opening_difference)
    summary.freeze_panes(1, 3)
    summary.autofilter(0, 0, max(len(pairs), 1), len(head) - 1)

    # Por categoría ------------------------------------------------------ #
    for col, (title, width) in enumerate([('Categoría', 40), ('Líneas', 10), ('Efecto S/', 18),
                                          ('Pendientes', 12), ('Qué hacer', 90)]):
        by_category.write(0, col, title, fmt['head'])
        by_category.set_column(col, col, width)
    row = 1
    for key, label in categories:
        category_lines = lines.filtered(lambda line, key=key: line.category == key)
        if not category_lines:
            continue
        by_category.write(row, 0, label, fmt['text'])
        by_category.write_number(row, 1, len(category_lines), fmt['text'])
        by_category.write_number(row, 2, sum(category_lines.mapped('effect_pen')), fmt['money'])
        by_category.write_number(row, 3, len(category_lines.filtered(lambda line: line.status == 'pending')), fmt['text'])
        by_category.write(row, 4, CATEGORY_HINTS.get(key, ''), fmt['wrap'])
        row += 1

    # Emparejamientos manuales ------------------------------------------- #
    matches_sheet = workbook.add_worksheet('Emparejamientos manuales')
    for col, (title, width) in enumerate([('Quién', 20), ('Cuándo', 17), ('Asientos unidos', 60),
                                          ('Diferencia aceptada S/', 18), ('Motivo', 50)]):
        matches_sheet.write(0, col, title, fmt['head'])
        matches_sheet.set_column(col, col, width)
    matches = run.env['ic.reconciliation.manual.match'].sudo().search([])
    for row, match in enumerate(matches, start=1):
        matches_sheet.write(row, 0, match.user_id.name or '', fmt['text'])
        matches_sheet.write_datetime(row, 1, match.date, fmt['date'])
        matches_sheet.write(row, 2, ', '.join((match.line_ids_a | match.line_ids_b).move_id.mapped('name')), fmt['wrap'])
        matches_sheet.write_number(row, 3, match.difference_pen, fmt['money'])
        matches_sheet.write(row, 4, match._reason_text(), fmt['wrap'])

    # Reglas ------------------------------------------------------------- #
    rules = workbook.add_worksheet('Reglas')
    rules.set_column(0, 0, 8)
    rules.set_column(1, 1, 45)
    rules.set_column(2, 2, 30)
    rules.write_row(0, 0, ['Orden', 'Regla', 'Parámetro'], fmt['head'])
    params = config._engine_params()
    parameters = {
        4: f"total {params.get('document_total_tolerance', 0.01)}; redondeo hasta {config.rounding_tolerance}; "
           f"tipo de cambio {config.rate_diff_percent} % o S/ {config.rate_diff_minimum}",
        5: f"{config.amount_tolerance}", 6: f"{config.amount_tolerance} · {config.number_days} días",
        10: f"{config.amount_tolerance} · {config.payment_days} días",
        11: f"{config.other_currency_percent} % o S/ {config.other_currency_minimum} · {config.payment_days} días",
        12: f"{config.amount_tolerance} · {config.grouped_days} días",
        13: f"{config.amount_tolerance} · {config.triangular_days} días",
        16: f"S/ {config.combination_tolerance} · {config.grouped_days} días",
        17: f"S/ {config.combination_tolerance} · {config.grouped_days} días · 2 o 3 partidas",
        18: f"S/ {config.combination_tolerance}",
    }
    for row, (number, name) in enumerate(RULES, start=1):
        rules.write_number(row, 0, number, fmt['text'])
        rules.write(row, 1, name, fmt['text'])
        rules.write(row, 2, parameters.get(number, ''), fmt['text'])

    workbook.close()
    return base64.b64encode(buffer.getvalue())


def _to_datetime(value):
    from datetime import datetime
    return datetime(value.year, value.month, value.day)
