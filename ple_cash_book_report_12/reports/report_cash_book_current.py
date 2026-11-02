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


# Indices de columnas (0-based)
COL_NRO_REG = 0     # A
COL_FECHA_OP = 1    # B
COL_DESC = 2        # C
COL_TD = 3          # D
COL_NRO_REF = 4     # E
COL_FECHA_REF = 5   # F
COL_MON = 6         # G
COL_CONTRA_CODE = 7 # H
COL_CONTRA_NAME = 8 # I
COL_DEUDOR = 9      # J
COL_ACREEDOR = 10   # K
COL_SALDO = 11      # L


class CashBookCurrentReportExcel(object):
    """Genera el Excel del PLE Libro Caja y Bancos - Formato 1.2.

    Layout: cabecera Formato 1.2 (5 filas) + encabezado de tabla (2 filas
    con merges) + bloques por cuenta (cabecera gris + SALDO ANTERIOR +
    filas de contrapartida). El bloque cabecera + encabezado se repite al
    inicio de cada mes. Sin filas TOTAL/SALDO ACTUAL al cierre de cuenta.
    """

    def __init__(self, obj, data):
        self.obj = obj
        self.data = data
        self._formats = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _currency_label(self):
        company = self.obj.company_id
        code = (company.currency_id.name or '').upper() if company else ''
        return 'SOLES' if code == 'PEN' else code

    # ------------------------------------------------------------------
    # Generacion
    # ------------------------------------------------------------------
    def get_content(self):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = workbook.add_worksheet('Libro Caja 1.2')

        ws.set_landscape()
        ws.set_paper(9)                        # 9 = A4
        ws.set_margins(0.2, 0.2, 0.3, 0.3)     # left, right, top, bottom
        ws.fit_to_pages(1, 0)                  # 12 columnas en una pagina de ancho

        
        self._register_formats(workbook)
        self._set_columns(ws)

        row = 0
        for month_block in self.data:
            row = self._write_report_header(ws, row, month_block['label'])
            row = self._write_table_header(ws, row)
            for account_block in month_block['accounts']:
                row = self._write_account_block(ws, row, account_block)
            row += 2  # separador entre meses

        workbook.close()
        output.seek(0)
        return output.read()

    def get_filename(self):
        company = self.obj.company_id
        period = self.obj.date_start.strftime('%Y%m') if self.obj.date_start else ''
        safe_name = ''.join(
            c if c.isalnum() else '_' for c in (company.name or 'company')
        )
        return 'Libro_Caja_1.2_%s_%s.xlsx' % (safe_name, period)

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
        f['num'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': '#,##0.00;-#,##0.00;"-"',
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

    def _set_columns(self, ws):
        ws.set_column(COL_NRO_REG,     COL_NRO_REG,     15)
        ws.set_column(COL_FECHA_OP,    COL_FECHA_OP,    12)
        ws.set_column(COL_DESC,        COL_DESC,        40)
        ws.set_column(COL_TD,          COL_TD,           6)
        ws.set_column(COL_NRO_REF,     COL_NRO_REF,     15)
        ws.set_column(COL_FECHA_REF,   COL_FECHA_REF,   12)
        ws.set_column(COL_MON,         COL_MON,          6)
        ws.set_column(COL_CONTRA_CODE, COL_CONTRA_CODE, 12)
        ws.set_column(COL_CONTRA_NAME, COL_CONTRA_NAME, 40)
        ws.set_column(COL_DEUDOR,      COL_DEUDOR,      14)
        ws.set_column(COL_ACREEDOR,    COL_ACREEDOR,    14)
        ws.set_column(COL_SALDO,       COL_SALDO,       14)

    # ------------------------------------------------------------------
    # Bloques
    # ------------------------------------------------------------------
    def _write_report_header(self, ws, row, period_label):
        company = self.obj.company_id
        f = self._formats

        ws.write(row,     0, 'Formato 1.2',
                 f['hdr_lbl'])
        ws.write(row,     1,
                 'Libro de Caja y Bancos - Detalle de los Movimientos de la Cuenta Corriente',
                 f['hdr_val'])
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
        """Escribe encabezado de tabla en 2 filas con merges."""
        f = self._formats
        ws.set_row(row,     22)
        ws.set_row(row + 1, 32)

        ws.merge_range(row, COL_NRO_REG,   row + 1, COL_NRO_REG,
                       'NUMERO REGISTRO', f['col'])
        ws.merge_range(row, COL_FECHA_OP,  row + 1, COL_FECHA_OP,
                       'FECHA OPERACION', f['col'])
        ws.merge_range(row, COL_DESC,      row + 1, COL_DESC,
                       'DESCRIPCION OPERACION', f['col'])
        ws.merge_range(row, COL_TD,        row, COL_FECHA_REF,
                       'DOCUMENTO TRANSACCION', f['group'])
        ws.merge_range(row, COL_MON,       row + 1, COL_MON,
                       'MON', f['col'])
        ws.merge_range(row, COL_CONTRA_CODE, row, COL_CONTRA_NAME,
                       'CUENTA CONTABLE ASOCIADA', f['group'])
        ws.merge_range(row, COL_DEUDOR,    row, COL_SALDO,
                       'SALDOS Y MOVIMIENTOS', f['group'])

        ws.write(row + 1, COL_TD,          'TD',          f['col'])
        ws.write(row + 1, COL_NRO_REF,     'NUMERO',      f['col'])
        ws.write(row + 1, COL_FECHA_REF,   'FECHA',       f['col'])
        ws.write(row + 1, COL_CONTRA_CODE, 'CODIGO',      f['col'])
        ws.write(row + 1, COL_CONTRA_NAME, 'DENOMINACION', f['col'])
        ws.write(row + 1, COL_DEUDOR,      'DEUDOR',      f['col'])
        ws.write(row + 1, COL_ACREEDOR,    'ACREEDOR',    f['col'])
        ws.write(row + 1, COL_SALDO,       'SALDO',       f['col'])

        return row + 2

    def _write_account_block(self, ws, row, account_block):
        f = self._formats

        # Cabecera de cuenta gris
        ws.write(row, 0, account_block['account_code'], f['account_code'])
        ws.merge_range(row, 1, row, COL_SALDO,
                       account_block['account_name'], f['account_name'])
        row += 1

        # SALDO ANTERIOR: label en A:K, valor en L
        ws.merge_range(row, COL_NRO_REG, row, COL_ACREEDOR,
                       'SALDO ANTERIOR', f['special_lbl'])
        ws.write_number(row, COL_SALDO,
                        account_block['saldo_anterior'], f['special_num'])
        row += 1

        # Filas de contrapartida
        for line in account_block['lines']:
            row = self._write_movement_row(ws, row, line)

        return row

    def _write_movement_row(self, ws, row, line):
        f = self._formats

        ws.write(row, COL_NRO_REG, line.get('nro_registro') or '', f['txt'])

        fecha = line.get('fecha_op')
        if isinstance(fecha, (date, datetime)):
            ws.write_datetime(row, COL_FECHA_OP, fecha, f['date'])
        else:
            ws.write(row, COL_FECHA_OP, fecha or '', f['txt'])

        ws.write(row, COL_DESC, line.get('descripcion') or '', f['txt'])
        ws.write(row, COL_TD,   line.get('td') or '',           f['txt_center'])
        ws.write(row, COL_NRO_REF, line.get('nro_ref') or '',   f['txt'])

        fecha_ref = line.get('fecha_ref')
        if isinstance(fecha_ref, (date, datetime)):
            ws.write_datetime(row, COL_FECHA_REF, fecha_ref, f['date'])
        else:
            ws.write(row, COL_FECHA_REF, fecha_ref or '', f['txt'])

        ws.write(row, COL_MON, line.get('mon') or '', f['txt_center'])
        ws.write(row, COL_CONTRA_CODE, line.get('contra_code') or '', f['txt'])
        ws.write(row, COL_CONTRA_NAME, line.get('contra_name') or '', f['txt'])

        ws.write_number(row, COL_DEUDOR,   float(line.get('deudor') or 0.0),   f['num'])
        ws.write_number(row, COL_ACREEDOR, float(line.get('acreedor') or 0.0), f['num'])
        ws.write_number(row, COL_SALDO,    float(line.get('saldo') or 0.0),    f['num'])

        return row + 1
