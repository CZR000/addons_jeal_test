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

# Indices de columnas (0-based) para xlsxwriter
COL_FECHA_OP = 0    # A
COL_NRO_COMP = 1    # B
COL_DESC = 2        # C
COL_TD = 3          # D
COL_NRO_REF = 4     # E
COL_FECHA_REF = 5   # F
COL_ANEXO = 6       # G
COL_DEBE = 7        # H
COL_HABER = 8       # I


class LedgerBookReportExcel(object):
    """Genera el Excel del PLE Libro Mayor Formato 6.1.

    Layout: cabecera de identificacion (5 filas) + encabezado de tabla
    (2 filas con merges) + bloques por cuenta (cabecera gris, SALDO
    ANTERIOR, movimientos, TOTAL MOVIMIENTO CUENTA, SALDO ACTUAL). Todo
    en una sola hoja continua; el bloque cabecera + encabezado de tabla
    se repite al inicio de cada mes.
    """

    def __init__(self, obj, data):
        self.obj = obj
        self.data = data
        self._formats = {}

    # ------------------------------------------------------------------
    # Helpers de cabecera
    # ------------------------------------------------------------------
    def _currency_label(self):
        company = self.obj.company_id
        code = (company.currency_id.name or '').upper() if company else ''
        return 'SOLES' if code == 'PEN' else code

    def _period_label(self):
        """Etiqueta del periodo para el reporte vacio: 'ENERO DE 2026' o
        'ENERO DE 2026 - MARZO DE 2026' si el rango abarca varios meses."""
        ds, de = self.obj.date_start, self.obj.date_end
        if not ds:
            return ''
        start = '%s DE %d' % (MONTHS_ES.get(ds.month, ''), ds.year)
        if not de or (ds.year, ds.month) == (de.year, de.month):
            return start
        end = '%s DE %d' % (MONTHS_ES.get(de.month, ''), de.year)
        return '%s - %s' % (start, end)
    
    # ------------------------------------------------------------------
    # Generacion
    # ------------------------------------------------------------------
    def get_content(self):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = workbook.add_worksheet('Libro Mayor 6.1')

        # --- Configuracion de impresion (para la conversion a PDF) ---
        ws.set_landscape()
        ws.set_paper(9)                        # 9 = A4
        ws.set_margins(0.2, 0.2, 0.3, 0.3)     # left, right, top, bottom (pulgadas)
        ws.fit_to_pages(1, 0)                  # 1 pagina de ancho, alto libre
        ws.repeat_rows(0, 6)

        self._register_formats(workbook)
        self._set_columns(ws)

        row = 0
        if not self.data:
            # Sin informacion: cabecera + encabezado de tabla + aviso
            row = self._write_report_header(ws, row, self._period_label())
            row = self._write_table_header(ws, row)
            self._write_empty_row(ws, row)
        else:
            for month_block in self.data:
                row = self._write_report_header(ws, row, month_block['label'])
                row = self._write_table_header(ws, row)
                for account_block in month_block['accounts']:
                    row = self._write_account_block(ws, row, account_block)
                # Separador visual entre meses
                row += 2

        workbook.close()
        output.seek(0)
        return output.read()

    def get_filename(self):
        company = self.obj.company_id
        period = self.obj.date_start.strftime('%Y%m') if self.obj.date_start else ''
        safe_name = ''.join(
            c if c.isalnum() else '_' for c in (company.name or 'company')
        )
        return 'Libro_Mayor_6.1_%s_%s.xlsx' % (safe_name, period)

    # ------------------------------------------------------------------
    # Formatos y anchos
    # ------------------------------------------------------------------
    def _register_formats(self, workbook):
        f = self._formats

        f['hdr_lbl'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
        })
        f['hdr_val'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter',
        })

        f['group'] = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#D9E1F2',
        })
        f['col'] = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#D9E1F2',
            'text_wrap': True,
        })

        f['account_code'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#BFBFBF',
        })
        f['account_name'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#BFBFBF',
        })

        f['txt'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
        })
        f['txt_center'] = workbook.add_format({
            'size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter',
        })
        f['date'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': 'dd/mm/yy',
        })
        f['date_ref'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': 'dd/mm/yyyy',
        })
        f['num'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': '#,##0.00',
        })

        f['special_lbl'] = workbook.add_format({
            'bold': True, 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#F2F2F2',
        })
        f['special_num'] = workbook.add_format({
            'bold': True, 'border': 1, 'size': 10, 'valign': 'vcenter',
            'num_format': '#,##0.00', 'bg_color': '#F2F2F2',
        })
        f['special_blank'] = workbook.add_format({
            'border': 1, 'size': 10, 'bg_color': '#F2F2F2',
        })

        f['empty'] = workbook.add_format({
            'italic': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10,
        })

    def _set_columns(self, ws):
        ws.set_column(COL_FECHA_OP,  COL_FECHA_OP,  12)
        ws.set_column(COL_NRO_COMP,  COL_NRO_COMP,  15)
        ws.set_column(COL_DESC,      COL_DESC,      40)
        ws.set_column(COL_TD,        COL_TD,         6)
        ws.set_column(COL_NRO_REF,   COL_NRO_REF,   15)
        ws.set_column(COL_FECHA_REF, COL_FECHA_REF, 12)
        ws.set_column(COL_ANEXO,     COL_ANEXO,     15)
        ws.set_column(COL_DEBE,      COL_DEBE,      15)
        ws.set_column(COL_HABER,     COL_HABER,     15)

    # ------------------------------------------------------------------
    # Bloques
    # ------------------------------------------------------------------
    def _write_empty_row(self, ws, row):
        """Fila de aviso cuando el reporte no tiene informacion."""
        ws.merge_range(row, COL_FECHA_OP, row, COL_HABER,
                       'SIN MOVIMIENTOS EN EL PERIODO', self._formats['empty'])
        return row + 1

    def _write_report_header(self, ws, row, period_label):
        """Escribe la cabecera Formato 6.1 (5 filas). Devuelve el proximo row."""
        company = self.obj.company_id
        f = self._formats

        ws.write(row,     0, 'Formato 6.1',   f['hdr_lbl'])
        ws.write(row,     1, 'Libro Mayor',    f['hdr_val'])
        ws.write(row + 1, 0, 'Periodo',        f['hdr_lbl'])
        ws.write(row + 1, 1, period_label,     f['hdr_val'])
        ws.write(row + 2, 0, 'RUC',            f['hdr_lbl'])
        ws.write(row + 2, 1, company.vat or '', f['hdr_val'])
        ws.write(row + 3, 0, 'Razon Social',   f['hdr_lbl'])
        ws.write(row + 3, 1, company.name or '', f['hdr_val'])
        ws.write(row + 4, 0, 'Expresado en',   f['hdr_lbl'])
        ws.write(row + 4, 1, self._currency_label(), f['hdr_val'])

        return row + 5

    def _write_table_header(self, ws, row):
        """Escribe el encabezado de tabla (2 filas con merges).
        Devuelve el proximo row."""
        f = self._formats
        ws.set_row(row,     22)
        ws.set_row(row + 1, 32)

        ws.merge_range(row, COL_FECHA_OP,  row + 1, COL_FECHA_OP,
                       'FECHA OPERACION', f['col'])
        ws.merge_range(row, COL_NRO_COMP,  row + 1, COL_NRO_COMP,
                       'NUMERO COMPROBANTE', f['col'])
        ws.merge_range(row, COL_DESC,      row + 1, COL_DESC,
                       'DESCRIPCION DE LA OPERACION', f['col'])
        ws.merge_range(row, COL_TD,        row,     COL_FECHA_REF,
                       'DOCUMENTO REFERENCIA', f['group'])
        ws.merge_range(row, COL_ANEXO,     row + 1, COL_ANEXO,
                       'CODIGO ANEXO', f['col'])
        ws.merge_range(row, COL_DEBE,      row,     COL_HABER,
                       'MOVIMIENTO', f['group'])

        ws.write(row + 1, COL_TD,        'TD',     f['col'])
        ws.write(row + 1, COL_NRO_REF,   'NUMERO', f['col'])
        ws.write(row + 1, COL_FECHA_REF, 'FECHA',  f['col'])
        ws.write(row + 1, COL_DEBE,      'DEBE',   f['col'])
        ws.write(row + 1, COL_HABER,     'HABER',  f['col'])

        return row + 2

    def _write_account_block(self, ws, row, account_block):
        """Escribe el bloque de una cuenta: cabecera gris + SALDO ANTERIOR +
        movimientos + TOTAL + SALDO ACTUAL. Devuelve el proximo row."""
        f = self._formats

        # ---- Fila cabecera de cuenta (gris) ----
        ws.write(row, 0, account_block['account_code'], f['account_code'])
        ws.merge_range(row, 1, row, COL_HABER,
                       account_block['account_name'], f['account_name'])
        row += 1

        # ---- SALDO ANTERIOR ----
        row = self._write_special_row(
            ws, row, 'SALDO ANTERIOR', account_block['saldo_anterior'],
        )

        # ---- Movimientos ----
        for line in account_block['lines']:
            row = self._write_movement_row(ws, row, line)

        # ---- TOTAL MOVIMIENTO CUENTA ----
        row = self._write_totals_row(
            ws, row,
            'TOTAL MOVIMIENTO CUENTA',
            account_block['total_debit'],
            account_block['total_credit'],
        )

        # ---- SALDO ACTUAL ----
        row = self._write_special_row(
            ws, row, 'SALDO ACTUAL', account_block['saldo_actual'],
        )

        return row

    def _write_movement_row(self, ws, row, line):
        f = self._formats

        fecha = line.get('fecha_op')
        if isinstance(fecha, (date, datetime)):
            ws.write_datetime(row, COL_FECHA_OP, fecha, f['date'])
        else:
            ws.write(row, COL_FECHA_OP, fecha or '', f['txt'])

        ws.write(row, COL_NRO_COMP, line.get('nro_comprobante') or '', f['txt'])
        ws.write(row, COL_DESC,     line.get('descripcion') or '',     f['txt'])
        ws.write(row, COL_TD,       line.get('td') or '',              f['txt_center'])
        ws.write(row, COL_NRO_REF,  line.get('nro_ref') or '',         f['txt'])

        fecha_ref = line.get('fecha_ref')
        if isinstance(fecha_ref, (date, datetime)):
            ws.write_datetime(row, COL_FECHA_REF, fecha_ref, f['date_ref'])
        else:
            ws.write(row, COL_FECHA_REF, fecha_ref or '', f['txt'])

        ws.write(row, COL_ANEXO, line.get('anexo') or '', f['txt'])

        debit = float(line.get('debit') or 0.0)
        credit = float(line.get('credit') or 0.0)
        # En movimientos siempre escribimos numero (0.00 si vacio) para
        # mantener el formato de bordes/alineacion consistente.
        ws.write_number(row, COL_DEBE,  debit,  f['num'])
        ws.write_number(row, COL_HABER, credit, f['num'])

        return row + 1

    def _write_special_row(self, ws, row, label, saldo):
        """Fila tipo SALDO ANTERIOR / SALDO ACTUAL: etiqueta en A:G y valor
        en DEBE o HABER segun el signo."""
        f = self._formats

        ws.merge_range(row, COL_FECHA_OP, row, COL_ANEXO,
                       label, f['special_lbl'])

        if saldo >= 0:
            ws.write_number(row, COL_DEBE, saldo, f['special_num'])
            ws.write_blank(row, COL_HABER, None, f['special_blank'])
        else:
            ws.write_blank(row, COL_DEBE, None, f['special_blank'])
            ws.write_number(row, COL_HABER, abs(saldo), f['special_num'])

        return row + 1

    def _write_totals_row(self, ws, row, label, total_debit, total_credit):
        """Fila TOTAL MOVIMIENTO CUENTA: etiqueta en A:G y ambas sumas."""
        f = self._formats

        ws.merge_range(row, COL_FECHA_OP, row, COL_ANEXO,
                       label, f['special_lbl'])
        ws.write_number(row, COL_DEBE,  total_debit,  f['special_num'])
        ws.write_number(row, COL_HABER, total_credit, f['special_num'])

        return row + 1
