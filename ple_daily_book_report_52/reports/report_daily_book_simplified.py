# -*- coding: utf-8 -*-
"""Formato 5.2 - Libro Diario de Formato Simplificado (matricial).

Una fila por asiento y una columna por cuenta agrupada a N digitos; cada
celda es el neto del asiento en esa cuenta (Debe - Haber): cargo en
positivo, abono entre parentesis. Celda vacia si la cuenta no se movio en
el asiento; 0.00 si se movio con neto cero.

Salidas:
  - Excel (pdf=False): una sola hoja con todas las cuentas usadas, sin
    partir en bloques, para cuadrar contra el PDF.
  - PDF (pdf=True), hoja unica: si el periodo tiene hasta
    `single_max_cols` cuentas, todos los folios llevan todas las cuentas
    como columnas fijas (igual que el Excel), en tramos de `max_rows`
    asientos; en A3 horizontal si las cuentas superan `max_cols`, si no en
    A4. El ultimo folio lleva el Total del periodo y el cuadre.
  - PDF (pdf=True), columnas por folio (mas cuentas que
    `single_max_cols`): A4 horizontal, una hoja (folio) por pagina. Cada
    asiento se imprime una sola vez, en una sola linea, con todas sus
    cuentas: los asientos se agrupan en folios de hasta `max_rows` filas
    cuyas cuentas juntas no superen `max_cols` columnas; las columnas de
    cada folio son solo las cuentas que mueven sus asientos. Un asiento con
    mas de `max_cols` cuentas va solo en su folio, con todas sus columnas
    (la pagina se reduce a escala para que entre). Cada folio lleva Total
    del folio y Total acumulado de sus cuentas (el acumulado incluye los
    folios anteriores aunque la cuenta no figure en ellos). Al final, el
    Resumen del periodo con el total de cada cuenta y el cuadre
    deudor = acreedor.

Estructura de `data` (la arma el modelo):
    {
        'digits_label': '4 DÍGITOS' | 'CÓDIGO COMPLETO' | ...,
        'accounts': [{'code': '1041', 'name': 'Ctas. corrientes ...'}, ...],
        'moves': [
            {'correl': '0001', 'cuo': 'CAMBI/2026/08/0001',
             'fecha': date, 'glosa': '...', 'nets': {'1041': -137.97, ...}},
            ...
        ],
    }
"""
from datetime import date, datetime
from io import BytesIO

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


MONTHS_ES = {
    1: 'ENERO', 2: 'FEBRERO', 3: 'MARZO', 4: 'ABRIL',
    5: 'MAYO', 6: 'JUNIO', 7: 'JULIO', 8: 'AGOSTO',
    9: 'SEPTIEMBRE', 10: 'OCTUBRE', 11: 'NOVIEMBRE', 12: 'DICIEMBRE',
}

# Bloques de columnas por primer digito del codigo (elemento PCGE)
BLOCKS = [
    ('12345', 'ACTIVO, PASIVO Y PATRIMONIO'),
    ('678', 'GASTOS E INGRESOS'),
    ('9', 'CUENTAS ANALÍTICAS DE EXPLOTACIÓN'),
    ('0', 'CUENTAS DE ORDEN'),
]
_ANALYTIC_BLOCK = 2  # indice de ('9', ...) en BLOCKS; incluye la 79
# Etiqueta corta del bloque cuando ocupa una sola columna
BLOCK_SHORT_LABELS = {
    'ACTIVO, PASIVO Y PATRIMONIO': 'ACT./PAS./PAT.',
    'GASTOS E INGRESOS': 'GAST./ING.',
    'CUENTAS ANALÍTICAS DE EXPLOTACIÓN': 'ANALÍTICAS',
    'CUENTAS DE ORDEN': 'ORDEN',
}

# Columnas fijas (0-based)
COL_NUM = 0
COL_CUO = 1
COL_FECHA = 2
COL_GLOSA = 3
COL_ACC = 4

NUM_FORMAT = '#,##0.00;(#,##0.00);0.00'

PDF_FOOTER_NOTE = (
    'Cargos en positivo, abonos entre paréntesis. Importe neto por cuenta '
    'y por asiento. Cada asiento figura una sola vez, completo en una línea; '
    'las columnas de cada folio son las cuentas que mueven sus asientos.'
)
PDF_FOOTER_NOTE_SINGLE = (
    'Cargos en positivo, abonos entre paréntesis. Importe neto por cuenta '
    'y por asiento. Cada asiento figura una sola vez, completo en una línea; '
    'columnas: todas las cuentas movidas en el período.'
)

# Glosa en el PDF: se recorta con "…" para que cada fila ocupe una linea
# (alto fijo = paginacion exacta).
PDF_GLOSA_MAX_CHARS = 52
ACC_NAME_MAX_CHARS = 40

# Alto de las filas de asientos y totales en el PDF (puntos). Con 30
# asientos por folio llenan la hoja: A3 en hoja unica, A4 en el resto.
PDF_ROW_HEIGHT_A4 = 16
PDF_ROW_HEIGHT_A3 = 24


def _block_index(code):
    # La 79 (cargas imputables a cuentas de costos) es la contrapartida de
    # las 9x en los asientos de destino: va en el bloque analitico para que
    # el AED quede completo en un solo folio.
    if (code or '').startswith('79'):
        return _ANALYTIC_BLOCK
    first = (code or '')[:1]
    for idx, (digits, _name) in enumerate(BLOCKS):
        if first in digits:
            return idx
    return 0


def _truncate(text, max_chars):
    text = (text or '').strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1].rstrip() + '…'


def _chunks(seq, size):
    return [seq[i:i + size] for i in range(0, len(seq), size)]


class DailyBookSimplifiedReportExcel(object):
    """Genera el Formato 5.2 matricial en Excel o en el XLSX para el PDF."""

    def __init__(self, obj, data, pdf=False, max_cols=10, max_rows=30,
                 single_max_cols=0):
        self.obj = obj
        self.data = data or {}
        self.pdf = pdf
        self.max_cols = max(1, int(max_cols or 10))
        self.max_rows = max(1, int(max_rows or 30))
        self.single_max_cols = max(0, int(single_max_cols or 0))
        self._formats = {}

        self.accounts = self.data.get('accounts') or []
        self.moves = self.data.get('moves') or []
        self.codes = [a['code'] for a in self.accounts]
        self.names = {a['code']: a.get('name') or '' for a in self.accounts}

    # ------------------------------------------------------------------
    # Datos de cabecera
    # ------------------------------------------------------------------
    def _period_label(self):
        d = self.obj.date_start
        if not d:
            return ''
        return '%s %d' % (MONTHS_ES.get(d.month, ''), d.year)

    def _currency(self):
        company = self.obj.company_id
        code = (company.currency_id.name or '').upper() if company else ''
        label = 'SOLES' if code == 'PEN' else code
        symbol = 'S/' if code == 'PEN' else (company.currency_id.symbol or code)
        return label, symbol

    def _digits_label(self):
        return self.data.get('digits_label') or ''

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def get_content(self):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        self._register_formats(workbook)
        if self.pdf:
            # Una hoja por folio: LibreOffice escala cada hoja por separado,
            # asi un folio mas ancho no achica a los demas.
            self._build_pdf(workbook)
        else:
            self._build_excel_sheet(workbook.add_worksheet('Formato 5.2'))
        workbook.close()
        output.seek(0)
        return output.read()

    def get_filename(self):
        company = self.obj.company_id
        period = self.obj.date_start.strftime('%Y%m') if self.obj.date_start else ''
        safe_name = ''.join(
            c if c.isalnum() else '_' for c in (company.name or 'company')
        )
        return 'Libro_Diario_5.2_%s_%s.xlsx' % (safe_name, period)

    # ------------------------------------------------------------------
    # Formatos
    # ------------------------------------------------------------------
    def _register_formats(self, workbook):
        f = self._formats
        base = 8
        f['title'] = workbook.add_format({'bold': True, 'size': 11})
        f['info'] = workbook.add_format({'size': base})
        f['info_bold'] = workbook.add_format({'size': base, 'bold': True})
        f['col'] = workbook.add_format({
            'bold': True, 'size': base, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#D9E1F2', 'text_wrap': True,
        })
        f['block'] = workbook.add_format({
            'bold': True, 'size': base - 1, 'align': 'center',
            'valign': 'vcenter', 'border': 1, 'bg_color': '#D9E1F2',
        })
        f['acc_cell'] = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1,
            'bg_color': '#D9E1F2', 'text_wrap': True, 'size': 6,
        })
        f['acc_code'] = workbook.add_format({'bold': True, 'size': base})
        f['acc_name'] = workbook.add_format({'size': 6})
        f['txt'] = workbook.add_format({
            'size': base, 'border': 1, 'valign': 'vcenter',
        })
        f['txt_center'] = workbook.add_format({
            'size': base, 'border': 1, 'valign': 'vcenter', 'align': 'center',
        })
        f['date'] = workbook.add_format({
            'size': base, 'border': 1, 'valign': 'vcenter', 'align': 'center',
            'num_format': 'dd/mm/yyyy',
        })
        f['num'] = workbook.add_format({
            'size': base, 'border': 1, 'valign': 'vcenter',
            'num_format': NUM_FORMAT,
        })
        f['blank'] = workbook.add_format({'border': 1})
        f['tot_lbl'] = workbook.add_format({
            'bold': True, 'size': base, 'border': 1, 'align': 'right',
            'valign': 'vcenter', 'bg_color': '#F2F2F2',
        })
        f['tot_num'] = workbook.add_format({
            'bold': True, 'size': base, 'border': 1, 'valign': 'vcenter',
            'bg_color': '#F2F2F2', 'num_format': NUM_FORMAT,
        })
        f['acum_lbl'] = workbook.add_format({
            'bold': True, 'size': base, 'border': 1, 'align': 'right',
            'valign': 'vcenter', 'bg_color': '#D9E1F2',
        })
        f['acum_num'] = workbook.add_format({
            'bold': True, 'size': base, 'border': 1, 'valign': 'vcenter',
            'bg_color': '#D9E1F2', 'num_format': NUM_FORMAT,
        })
        f['cuadre'] = workbook.add_format({'bold': True, 'size': base})
        f['empty'] = workbook.add_format({
            'italic': True, 'size': base, 'border': 1, 'align': 'center',
        })

    def _set_fixed_columns(self, ws, glosa_width):
        ws.set_column(COL_NUM, COL_NUM, 6)
        ws.set_column(COL_CUO, COL_CUO, 17)
        ws.set_column(COL_FECHA, COL_FECHA, 9.5)
        ws.set_column(COL_GLOSA, COL_GLOSA, glosa_width)

    # ------------------------------------------------------------------
    # Bloques comunes
    # ------------------------------------------------------------------
    def _write_table_header(self, ws, row, codes, group_label_by_col):
        """Encabezado de tabla en 2 filas:
          [N°][CUO][FECHA][GLOSA][   nombre del bloque   ]
          [  ][   ][     ][     ][ 1041 / nombre ][ ... ]
        group_label_by_col: [(col_ini, col_fin, etiqueta), ...]
        """
        f = self._formats
        ws.set_row(row, 13)
        ws.set_row(row + 1, 30)
        titles = [
            (COL_NUM, 'N° CORREL.'),
            (COL_CUO, 'CÓDIGO ÚNICO DE OPERACIÓN'),
            (COL_FECHA, 'FECHA'),
            (COL_GLOSA, 'GLOSA O DESCRIPCIÓN DE LA OPERACIÓN'),
        ]
        for col, title in titles:
            ws.merge_range(row, col, row + 1, col, title, f['col'])

        for c_ini, c_fin, label in group_label_by_col:
            if c_fin > c_ini:
                ws.merge_range(row, c_ini, row, c_fin, label, f['block'])
            else:
                ws.write(row, c_ini, BLOCK_SHORT_LABELS.get(label, label),
                         f['block'])

        for i, code in enumerate(codes):
            col = COL_ACC + i
            name = _truncate(self.names.get(code, ''), ACC_NAME_MAX_CHARS)
            if name:
                ws.write_rich_string(
                    row + 1, col,
                    f['acc_code'], code, f['acc_name'], '\n' + name,
                    f['acc_cell'],
                )
            else:
                ws.write(row + 1, col, code, f['acc_cell'])
        return row + 2

    def _write_move_row(self, ws, row, m, codes, glosa_max=None):
        f = self._formats
        ws.write(row, COL_NUM, m.get('correl') or '', f['txt_center'])
        ws.write(row, COL_CUO, m.get('cuo') or '', f['txt'])
        fecha = m.get('fecha')
        if isinstance(fecha, (date, datetime)):
            ws.write_datetime(row, COL_FECHA, fecha, f['date'])
        else:
            ws.write(row, COL_FECHA, fecha or '', f['txt_center'])
        glosa = m.get('glosa') or ''
        if glosa_max:
            glosa = _truncate(glosa, glosa_max)
        ws.write(row, COL_GLOSA, glosa, f['txt'])

        nets = m.get('nets') or {}
        for i, code in enumerate(codes):
            col = COL_ACC + i
            if code in nets:
                ws.write_number(row, col, round(nets[code], 2), f['num'])
            else:
                ws.write_blank(row, col, None, f['blank'])

    def _write_totals_row(self, ws, row, label, codes, totals, lbl_fmt, num_fmt):
        ws.merge_range(row, COL_NUM, row, COL_GLOSA, label, self._formats[lbl_fmt])
        for i, code in enumerate(codes):
            ws.write_number(row, COL_ACC + i, round(totals.get(code, 0.0), 2),
                            self._formats[num_fmt])

    def _period_totals(self):
        totals = {}
        for m in self.moves:
            for code, val in (m.get('nets') or {}).items():
                totals[code] = totals.get(code, 0.0) + val
        return totals

    def _cuadre_text(self, totals):
        _label, symbol = self._currency()
        debit = sum(v for v in totals.values() if v > 0)
        credit = -sum(v for v in totals.values() if v < 0)
        return (
            'CUADRE DEL PERÍODO: suma de saldos deudores %s %s  =  suma de '
            'saldos acreedores %s %s' % (
                symbol, '{:,.2f}'.format(round(debit, 2)),
                symbol, '{:,.2f}'.format(round(credit, 2)),
            )
        )

    def _block_groups(self, codes, col_start=COL_ACC):
        """Agrupa columnas consecutivas por bloque para la fila superior."""
        groups = []
        for i, code in enumerate(codes):
            b = _block_index(code)
            col = col_start + i
            if groups and groups[-1][3] == b:
                groups[-1][1] = col
            else:
                groups.append([col, col, BLOCKS[b][1], b])
        return [(g[0], g[1], g[2]) for g in groups]

    # ------------------------------------------------------------------
    # Excel: una sola hoja
    # ------------------------------------------------------------------
    def _build_excel_sheet(self, ws):
        f = self._formats
        company = self.obj.company_id
        currency_label, _sym = self._currency()

        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        self._set_fixed_columns(ws, 50)
        if self.codes:
            ws.set_column(COL_ACC, COL_ACC + len(self.codes) - 1, 11)

        ws.write(0, 0, 'FORMATO 5.2: "LIBRO DIARIO DE FORMATO SIMPLIFICADO"',
                 f['title'])
        ws.write(1, 0, 'PERÍODO: %s' % self._period_label(), f['info'])
        ws.write(2, 0, 'RUC: %s' % (company.vat or ''), f['info'])
        ws.write(3, 0, 'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL: %s'
                 % (company.name or ''), f['info'])
        ws.write(4, 0, 'EXPRESADO EN: %s     CUENTAS A %s'
                 % (currency_label, self._digits_label()), f['info'])

        row = 6
        if not self.moves:
            ws.merge_range(row, COL_NUM, row, COL_GLOSA,
                           'SIN MOVIMIENTOS EN EL PERÍODO', f['empty'])
            return

        row = self._write_table_header(ws, row, self.codes,
                                       self._block_groups(self.codes))
        ws.freeze_panes(row, COL_ACC)
        ws.repeat_rows(6, 7)

        for m in self.moves:
            ws.set_row(row, 12)
            self._write_move_row(ws, row, m, self.codes)
            row += 1

        totals = self._period_totals()
        self._write_totals_row(ws, row, 'TOTAL DEL PERÍODO', self.codes,
                               totals, 'acum_lbl', 'acum_num')
        row += 2
        ws.write(row, 0, self._cuadre_text(totals), f['cuadre'])

    # ------------------------------------------------------------------
    # PDF: un folio por hoja, cada asiento en una sola linea
    # ------------------------------------------------------------------
    def _build_folios(self):
        """[(asientos, [codigos]), ...]: agrupa asientos consecutivos
        mientras quepan en `max_rows` filas y `max_cols` cuentas. Un asiento
        con mas de `max_cols` cuentas queda solo en su folio."""
        folios = []
        cur, cur_codes = [], set()
        for m in self.moves:
            codes = set(m.get('nets') or {})
            if cur and (len(cur) >= self.max_rows
                        or len(cur_codes | codes) > self.max_cols):
                folios.append((cur, cur_codes))
                cur, cur_codes = [], set()
            cur.append(m)
            cur_codes |= codes
        if cur:
            folios.append((cur, cur_codes))
        return [(moves, sorted(codes)) for moves, codes in folios]

    def _single_sheet(self):
        """Hoja unica: todas las cuentas del periodo como columnas fijas."""
        return bool(self.single_max_cols
                    and len(self.codes) <= self.single_max_cols)

    def _setup_pdf_sheet(self, ws, n_cols, a3=False):
        """Pagina A4 (o A3) horizontal; ancho fijo de `max_cols` columnas
        de cuenta (todos los folios a la misma escala) salvo que el folio
        tenga mas."""
        ws.set_landscape()
        ws.set_paper(8 if a3 else 9)
        ws.set_margins(left=0.2, right=0.2, top=0.4, bottom=0.55)
        ws.fit_to_pages(1, 1)
        ws.set_footer(
            '&L&6%s&R&7Formato 5.2 - Página &P de &N' % (
                PDF_FOOTER_NOTE_SINGLE if self._single_sheet()
                else PDF_FOOTER_NOTE),
            {'margin': 0.2},
        )
        self._set_fixed_columns(ws, 36)
        width = max(self.max_cols, n_cols)
        ws.set_column(COL_ACC, COL_ACC + width - 1, 10)
        return COL_ACC + width - 1

    def _write_folio_header(self, ws, row, right_lines):
        f = self._formats
        company = self.obj.company_id
        info_left = [
            'PERÍODO: %s' % self._period_label(),
            'RUC: %s' % (company.vat or ''),
            'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL: %s'
            % (company.name or ''),
        ]
        ws.set_row(row, 16)
        ws.write(row, 0, 'FORMATO 5.2: "LIBRO DIARIO DE FORMATO SIMPLIFICADO"',
                 f['title'])
        row += 1
        for i, left in enumerate(info_left):
            ws.set_row(row, 11)
            ws.write(row, 0, left, f['info'])
            text, fmt = right_lines[i]
            ws.write(row, COL_ACC, text, f[fmt])
            row += 1
        ws.set_row(row, 5)
        return row + 1

    def _build_pdf(self, workbook):
        f = self._formats
        currency_label, _sym = self._currency()
        expressed = ('EXPRESADO EN: %s     CUENTAS A %s'
                     % (currency_label, self._digits_label()), 'info')

        if not self.moves:
            ws = workbook.add_worksheet('Folio 0001')
            last_col = self._setup_pdf_sheet(ws, self.max_cols)
            row = self._write_folio_header(
                ws, 0, [expressed, ('', 'info'), ('', 'info')])
            ws.merge_range(row, COL_NUM, row, last_col,
                           'SIN MOVIMIENTOS EN EL PERÍODO', f['empty'])
            return

        single = self._single_sheet()
        a3 = single and len(self.codes) > self.max_cols
        if single:
            folios = [(chunk, list(self.codes))
                      for chunk in _chunks(self.moves, self.max_rows)]
            summary_parts = []
        else:
            folios = self._build_folios()
            summary_parts = _chunks(self.codes, self.max_cols) or [[]]
        n_total = len(folios) + len(summary_parts)
        period_totals = self._period_totals()
        cumulative = {}
        row_h = PDF_ROW_HEIGHT_A3 if a3 else PDF_ROW_HEIGHT_A4

        for f_idx, (moves, codes) in enumerate(folios, start=1):
            ws = workbook.add_worksheet('Folio %04d' % f_idx)
            last_col = self._setup_pdf_sheet(ws, len(codes), a3=a3)
            is_last = single and f_idx == len(folios)

            folio_totals = {}
            for m in moves:
                for code, val in (m.get('nets') or {}).items():
                    folio_totals[code] = folio_totals.get(code, 0.0) + val
            for code, val in folio_totals.items():
                cumulative[code] = cumulative.get(code, 0.0) + val

            row = self._write_folio_header(ws, 0, [
                expressed,
                ('FOLIO %d DE %d' % (f_idx, n_total), 'info_bold'),
                ('Asientos %s al %s' % (moves[0].get('correl'),
                                        moves[-1].get('correl')), 'info'),
            ])
            row = self._write_table_header(ws, row, codes,
                                           self._block_groups(codes))
            for m in moves:
                ws.set_row(row, row_h)
                self._write_move_row(ws, row, m, codes,
                                     glosa_max=PDF_GLOSA_MAX_CHARS)
                row += 1
            ws.set_row(row, row_h)
            self._write_totals_row(ws, row, 'TOTAL DEL FOLIO', codes,
                                   folio_totals, 'tot_lbl', 'tot_num')
            row += 1
            ws.set_row(row, row_h)
            self._write_totals_row(
                ws, row, 'TOTAL DEL PERÍODO' if is_last else 'TOTAL ACUMULADO',
                codes, cumulative, 'acum_lbl', 'acum_num')
            if is_last:
                row += 1
                ws.set_row(row, 8)
                row += 1
                ws.set_row(row, 14)
                ws.write(row, 0, self._cuadre_text(period_totals),
                         f['cuadre'])
            ws.print_area(0, 0, row, last_col)

        # Resumen: total del periodo de todas las cuentas + cuadre
        n_parts = len(summary_parts)
        for p_idx, codes in enumerate(summary_parts, start=1):
            f_idx = len(folios) + p_idx
            ws = workbook.add_worksheet('Resumen %d' % p_idx)
            last_col = self._setup_pdf_sheet(ws, len(codes))
            label = 'RESUMEN DEL PERÍODO'
            if n_parts > 1:
                label = '%s (PARTE %d DE %d)' % (label, p_idx, n_parts)
            row = self._write_folio_header(ws, 0, [
                expressed,
                ('FOLIO %d DE %d: %s' % (f_idx, n_total, label), 'info_bold'),
                ('Asientos %s al %s' % (self.moves[0].get('correl'),
                                        self.moves[-1].get('correl')), 'info'),
            ])
            row = self._write_table_header(ws, row, codes,
                                           self._block_groups(codes))
            ws.set_row(row, row_h)
            self._write_totals_row(ws, row, 'TOTAL DEL PERÍODO', codes,
                                   period_totals, 'acum_lbl', 'acum_num')
            if p_idx == n_parts:
                row += 1
                ws.set_row(row, 8)
                row += 1
                ws.set_row(row, 14)
                ws.write(row, 0, self._cuadre_text(period_totals),
                         f['cuadre'])
            ws.print_area(0, 0, row, last_col)