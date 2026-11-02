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


class InvBalReportBase(object):
    """Base comun para los constructores de Excel de los formatos 3.x del
    Libro de Inventarios y Balances.

    Cada formato concreto hereda de esta clase y define:
      - FORMATO_CODE  (ej. '3.1')
      - FORMATO_TITLE (titulo oficial SUNAT del formato)
      - SHEET_NAME    (nombre de la hoja)
      - build(ws, workbook)  -> escribe el contenido del formato

    Reutiliza el patron del Libro Caja 1.1: registro de formatos de celda,
    cabecera estandar (Formato / Ejercicio / RUC / Razon Social) y el
    armado de get_content()/get_filename().
    """

    FORMATO_CODE = ''
    FORMATO_TITLE = ''
    SHEET_NAME = 'Reporte'
    LANDSCAPE = False

    def __init__(self, obj, data):
        self.obj = obj
        self.data = data
        self._formats = {}

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------
    def get_content(self, include_extra=True):
        """XLSX del formato. Con `include_extra` agrega las hojas de
        trabajo del formato; el PDF se arma sin ellas."""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        self.write_sheet(workbook)
        if include_extra:
            self.write_extra_sheets(workbook)
        workbook.close()
        output.seek(0)
        return output.read()

    def write_sheet(self, workbook):
        """Agrega la hoja del formato a `workbook` (propio o consolidado)."""
        ws = workbook.add_worksheet(self.SHEET_NAME)
        if self.LANDSCAPE:
            ws.set_landscape()
        ws.set_paper(9)                     # A4
        ws.set_margins(0.2, 0.2, 0.3, 0.5)
        ws.fit_to_pages(1, 0)
        ws.set_footer(
            '&L&8Formato %s&R&8Página &P de &N' % self.FORMATO_CODE,
            {'margin': 0.2},
        )
        # Los formatos de celda pertenecen a cada workbook.
        self._formats = {}
        self._register_formats(workbook)
        self.build(ws, workbook)
        return ws

    def get_filename(self):
        company = self.obj.company_id
        period = self.obj.date_end.strftime('%Y%m') if self.obj.date_end else ''
        safe = ''.join(
            c if c.isalnum() else '_' for c in (company.name or 'company')
        )
        code = self.FORMATO_CODE.replace('.', '_')
        return 'Libro_Inv_Bal_%s_%s_%s.xlsx' % (code, safe, period)

    def write_extra_sheets(self, workbook):
        """Hojas de trabajo adicionales del formato (solo van en el Excel,
        no en el PDF). Se llama despues de `write_sheet` sobre el mismo
        workbook, asi que puede usar `self._formats`. Por defecto ninguna."""
        return None

    # ------------------------------------------------------------------
    # A implementar por cada formato
    # ------------------------------------------------------------------
    def build(self, ws, workbook):
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Formatos de celda compartidos
    # ------------------------------------------------------------------
    def _register_formats(self, workbook):
        f = self._formats
        f['title'] = workbook.add_format({
            'bold': True, 'size': 11, 'align': 'center', 'valign': 'vcenter',
            'text_wrap': True,
        })
        f['hdr_lbl'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
        })
        f['hdr_val'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter',
        })
        f['col'] = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#D9E1F2', 'text_wrap': True,
        })
        f['section'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
            'bg_color': '#BFBFBF', 'border': 1,
        })
        f['line_lbl'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter', 'border': 1,
        })
        f['total_lbl'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#F2F2F2',
        })
        f['total_lbl_right'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#F2F2F2',
        })
        f['txt'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
        })
        f['txt_wrap'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter', 'text_wrap': True,
        })
        f['txt_center'] = workbook.add_format({
            'size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter',
        })
        f['date'] = workbook.add_format({
            'size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter',
            'num_format': 'dd/mm/yyyy',
        })
        f['num'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': '#,##0.00;-#,##0.00;"-"',
        })
        f['total_num'] = workbook.add_format({
            'bold': True, 'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': '#,##0.00;-#,##0.00;"-"', 'bg_color': '#F2F2F2',
        })
        f['blank'] = workbook.add_format({})

    # ------------------------------------------------------------------
    # Cabecera estandar SUNAT (Formato / Ejercicio / RUC / Razon Social)
    # ------------------------------------------------------------------
    def _write_standard_header(self, ws, row, span_last_col):
        """Escribe el bloque de cabecera comun. Retorna la fila siguiente."""
        company = self.obj.company_id
        f = self._formats

        title = 'FORMATO %s: "LIBRO DE INVENTARIOS Y BALANCES - %s"' % (
            self.FORMATO_CODE, (self.FORMATO_TITLE or '').upper(),
        )
        ws.set_row(row, 32)
        ws.merge_range(row, 0, row, span_last_col, title, f['title'])
        row += 2

        ws.write_rich_string(
            row, 0,
            f['hdr_lbl'], 'EJERCICIO:  ',
            f['hdr_val'], self.obj.date_end.strftime('%Y') if self.obj.date_end else '-',
        )
        row += 1
        ws.write_rich_string(
            row, 0,
            f['hdr_lbl'], 'RUC:  ',
            f['hdr_val'], company.vat or '-',
        )
        row += 1
        ws.write_rich_string(
            row, 0,
            f['hdr_lbl'], 'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL:  ',
            f['hdr_val'], company.name or '-',
        )
        row += 2
        return row

    # ------------------------------------------------------------------
    # Helpers de escritura
    # ------------------------------------------------------------------
    def _write_date(self, ws, row, col, value, fmt_key='date'):
        """Escribe una fecha (date/datetime) o texto si no es fecha."""
        f = self._formats
        if value and hasattr(value, 'year'):
            ws.write_datetime(row, col, value, f[fmt_key])
        else:
            ws.write(row, col, value or '', f['txt_center'])


# ===========================================================================
# Base para los formatos de detalle por tercero (3.3, 3.4, 3.5, 3.12)
# ===========================================================================
class InvBalPartnerReportBase(InvBalReportBase):
    """Base para los formatos de detalle por tercero (3.3, 3.4 y luego
    3.5, 3.12, 3.13...): tipo y numero de documento de identidad,
    nombre / razon social, monto y fecha.

    Cada formato define las etiquetas PARTY_LABEL, AMOUNT_LABEL y
    DATE_LABEL.

    `data` es el dict devuelto por _get_open_items():
        {'lines': [{doc_type, doc_number, name, amount, date}], 'total'}
    """

    PARTY_LABEL = 'INFORMACIÓN DEL CLIENTE'
    AMOUNT_LABEL = 'MONTO DE LA CUENTA POR COBRAR'
    DATE_LABEL = 'FECHA DE EMISIÓN DEL COMPROBANTE DE PAGO'

    COL_DOC_TYPE = 0
    COL_DOC_NUMBER = 1
    COL_NAME = 2
    COL_AMOUNT = 3
    COL_DATE = 4

    def build(self, ws, workbook):
        self._set_columns(ws)
        row = self._write_standard_header(ws, 0, self.COL_DATE)
        row = self._write_table_header(ws, row)
        for line in self.data.get('lines', []):
            row = self._write_line(ws, row, line)
        self._write_totals(ws, row)

    def _set_columns(self, ws):
        ws.set_column(self.COL_DOC_TYPE, self.COL_DOC_TYPE, 14)
        ws.set_column(self.COL_DOC_NUMBER, self.COL_DOC_NUMBER, 16)
        ws.set_column(self.COL_NAME, self.COL_NAME, 55)
        ws.set_column(self.COL_AMOUNT, self.COL_AMOUNT, 18)
        ws.set_column(self.COL_DATE, self.COL_DATE, 20)

    def _write_table_header(self, ws, row):
        f = self._formats
        ws.set_row(row, 20)
        ws.set_row(row + 1, 20)
        ws.set_row(row + 2, 30)
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_NAME,
                       self.PARTY_LABEL, f['col'])
        ws.merge_range(row, self.COL_AMOUNT, row + 2, self.COL_AMOUNT,
                       self.AMOUNT_LABEL, f['col'])
        ws.merge_range(row, self.COL_DATE, row + 2, self.COL_DATE,
                       self.DATE_LABEL, f['col'])
        ws.merge_range(row + 1, self.COL_DOC_TYPE, row + 1, self.COL_DOC_NUMBER,
                       'DOCUMENTO DE IDENTIDAD', f['col'])
        ws.merge_range(row + 1, self.COL_NAME, row + 2, self.COL_NAME,
                       'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL', f['col'])
        ws.write(row + 2, self.COL_DOC_TYPE, 'TIPO (TABLA 2)', f['col'])
        ws.write(row + 2, self.COL_DOC_NUMBER, 'NÚMERO', f['col'])
        return row + 3

    def _write_line(self, ws, row, line):
        f = self._formats
        ws.write_string(row, self.COL_DOC_TYPE, str(line.get('doc_type') or ''), f['txt_center'])
        ws.write_string(row, self.COL_DOC_NUMBER, line.get('doc_number') or '', f['txt'])
        ws.write_string(row, self.COL_NAME, line.get('name') or '', f['txt_wrap'])
        ws.write_number(row, self.COL_AMOUNT, float(line.get('amount') or 0.0), f['num'])
        self._write_date(ws, row, self.COL_DATE, line.get('date'))
        return row + 1

    def _write_totals(self, ws, row):
        f = self._formats
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_NAME,
                       'SALDO FINAL TOTAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_AMOUNT,
                        float(self.data.get('total') or 0.0), f['total_num'])
        ws.write_blank(row, self.COL_DATE, None, f['total_num'])
        return row + 1
