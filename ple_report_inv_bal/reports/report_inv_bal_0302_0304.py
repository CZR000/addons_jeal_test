from .report_inv_bal_base import InvBalReportBase, InvBalPartnerReportBase


class InvBal32ReportExcel(InvBalReportBase):
    """Formato 3.2 - Detalle del saldo de la cuenta 10 (Efectivo).

    Columnas: Cuenta contable divisionaria (codigo, denominacion) |
    Referencia de la cuenta (entidad financiera Tabla 3, numero de cuenta,
    tipo de moneda Tabla 4) | Saldo contable final (deudor, acreedor).

    `data` es el dict devuelto por _get_data_02():
        {'lines': [{code, name, bank_code, account_number, currency,
                    debit, credit}], 'total_debit', 'total_credit'}
    """

    FORMATO_CODE = '3.2'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 10 - Efectivo y equivalentes de efectivo'
    SHEET_NAME = 'F3.2 Efectivo'
    LANDSCAPE = True

    COL_CODE = 0
    COL_NAME = 1
    COL_BANK = 2
    COL_NUMBER = 3
    COL_CURRENCY = 4
    COL_DEBIT = 5
    COL_CREDIT = 6

    def build(self, ws, workbook):
        self._set_columns(ws)
        row = self._write_standard_header(ws, 0, self.COL_CREDIT)
        row = self._write_table_header(ws, row)
        for line in self.data.get('lines', []):
            row = self._write_line(ws, row, line)
        self._write_totals(ws, row)

    def _set_columns(self, ws):
        ws.set_column(self.COL_CODE, self.COL_CODE, 12)
        ws.set_column(self.COL_NAME, self.COL_NAME, 50)
        ws.set_column(self.COL_BANK, self.COL_BANK, 14)
        ws.set_column(self.COL_NUMBER, self.COL_NUMBER, 26)
        ws.set_column(self.COL_CURRENCY, self.COL_CURRENCY, 12)
        ws.set_column(self.COL_DEBIT, self.COL_CREDIT, 16)

    def _write_table_header(self, ws, row):
        f = self._formats
        ws.set_row(row, 22)
        ws.set_row(row + 1, 40)
        ws.merge_range(row, self.COL_CODE, row, self.COL_NAME,
                       'CUENTA CONTABLE DIVISIONARIA', f['col'])
        ws.merge_range(row, self.COL_BANK, row, self.COL_CURRENCY,
                       'REFERENCIA DE LA CUENTA', f['col'])
        ws.merge_range(row, self.COL_DEBIT, row, self.COL_CREDIT,
                       'SALDO CONTABLE FINAL', f['col'])
        headers = [
            'CÓDIGO', 'DENOMINACIÓN', 'ENTIDAD FINANCIERA (TABLA 3)',
            'NÚMERO DE LA CUENTA', 'TIPO DE MONEDA (TABLA 4)',
            'DEUDOR', 'ACREEDOR',
        ]
        for col, header in enumerate(headers):
            ws.write(row + 1, col, header, f['col'])
        return row + 2

    def _write_line(self, ws, row, line):
        f = self._formats
        ws.write_string(row, self.COL_CODE, line.get('code') or '', f['txt'])
        ws.write_string(row, self.COL_NAME, line.get('name') or '', f['txt_wrap'])
        ws.write_string(row, self.COL_BANK, line.get('bank_code') or '', f['txt_center'])
        ws.write_string(row, self.COL_NUMBER, line.get('account_number') or '', f['txt'])
        ws.write_string(row, self.COL_CURRENCY, line.get('currency') or '', f['txt_center'])
        ws.write_number(row, self.COL_DEBIT, float(line.get('debit') or 0.0), f['num'])
        ws.write_number(row, self.COL_CREDIT, float(line.get('credit') or 0.0), f['num'])
        return row + 1

    def _write_totals(self, ws, row):
        f = self._formats
        ws.merge_range(row, self.COL_CODE, row, self.COL_CURRENCY,
                       'TOTALES', f['total_lbl_right'])
        ws.write_number(row, self.COL_DEBIT,
                        float(self.data.get('total_debit') or 0.0), f['total_num'])
        ws.write_number(row, self.COL_CREDIT,
                        float(self.data.get('total_credit') or 0.0), f['total_num'])
        return row + 1


class InvBal33ReportExcel(InvBalPartnerReportBase):
    """Formato 3.3 - Clientes (cuenta 12)."""

    FORMATO_CODE = '3.3'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 12 - Clientes'
    SHEET_NAME = 'F3.3 Clientes'
    PARTY_LABEL = 'INFORMACIÓN DEL CLIENTE'
    AMOUNT_LABEL = 'MONTO DE LA CUENTA POR COBRAR'
    DATE_LABEL = 'FECHA DE EMISIÓN DEL COMPROBANTE DE PAGO'


class InvBal34ReportExcel(InvBalPartnerReportBase):
    """Formato 3.4 - Cuentas por cobrar al personal y accionistas (cuenta 14)."""

    FORMATO_CODE = '3.4'
    FORMATO_TITLE = ('Detalle del saldo de la cuenta 14 - Cuentas por cobrar al '
                     'personal, a los accionistas (socios), directores y gerentes')
    SHEET_NAME = 'F3.4 Personal y Accionistas'
    PARTY_LABEL = 'INFORMACIÓN DEL ACCIONISTA, SOCIO O PERSONAL'
    AMOUNT_LABEL = 'MONTO DE LA CUENTA POR COBRAR'
    DATE_LABEL = 'FECHA DE INICIO DE LA OPERACIÓN'
