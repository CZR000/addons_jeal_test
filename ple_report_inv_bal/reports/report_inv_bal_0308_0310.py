from .report_inv_bal_base import InvBalReportBase


class InvBal38ReportExcel(InvBalReportBase):
    """Formato 3.8 - Inversiones mobiliarias (cuenta 30).

    Columnas: Documento de identidad del emisor (tipo Tabla 2, numero),
    razon social del emisor | Titulo (denominacion, valor nominal unitario,
    cantidad) | Valor en libros (costo total, provision total, total neto).

    `data`: {'lines': [{doc_type, doc_number, name, title, nominal_value,
    quantity, cost, provision, net}], 'total_cost', 'total_provision',
    'total_net'}
    """

    FORMATO_CODE = '3.8'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 30 - Inversiones mobiliarias'
    SHEET_NAME = 'F3.8 Inv. mobiliarias'
    LANDSCAPE = True

    COL_DOC_TYPE = 0
    COL_DOC_NUMBER = 1
    COL_NAME = 2
    COL_TITLE = 3
    COL_NOMINAL = 4
    COL_QTY = 5
    COL_COST = 6
    COL_PROVISION = 7
    COL_NET = 8

    def build(self, ws, workbook):
        f = self._formats
        widths = [12, 15, 34, 40, 14, 12, 16, 16, 16]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)

        row = self._write_standard_header(ws, 0, self.COL_NET)

        ws.set_row(row, 22)
        ws.set_row(row + 1, 36)
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_DOC_NUMBER,
                       'DOCUMENTO DE IDENTIDAD', f['col'])
        ws.merge_range(row, self.COL_NAME, row + 1, self.COL_NAME,
                       'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL DEL EMISOR',
                       f['col'])
        ws.merge_range(row, self.COL_TITLE, row, self.COL_QTY, 'TÍTULO', f['col'])
        ws.merge_range(row, self.COL_COST, row, self.COL_NET, 'VALOR EN LIBROS', f['col'])
        sub = {
            self.COL_DOC_TYPE: 'TIPO (TABLA 2)',
            self.COL_DOC_NUMBER: 'NÚMERO',
            self.COL_TITLE: 'DENOMINACIÓN',
            self.COL_NOMINAL: 'VALOR NOMINAL UNITARIO',
            self.COL_QTY: 'CANTIDAD',
            self.COL_COST: 'COSTO TOTAL',
            self.COL_PROVISION: 'PROVISIÓN TOTAL',
            self.COL_NET: 'TOTAL NETO',
        }
        for col, label in sub.items():
            ws.write(row + 1, col, label, f['col'])
        row += 2

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_DOC_TYPE, str(line.get('doc_type') or ''), f['txt_center'])
            ws.write_string(row, self.COL_DOC_NUMBER, line.get('doc_number') or '', f['txt'])
            ws.write_string(row, self.COL_NAME, line.get('name') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_TITLE, line.get('title') or '', f['txt_wrap'])
            for col, key in ((self.COL_NOMINAL, 'nominal_value'), (self.COL_QTY, 'quantity')):
                value = line.get(key)
                if value is None:
                    ws.write_blank(row, col, None, f['txt'])
                else:
                    ws.write_number(row, col, float(value), f['num'])
            ws.write_number(row, self.COL_COST, float(line.get('cost') or 0.0), f['num'])
            ws.write_number(row, self.COL_PROVISION, float(line.get('provision') or 0.0), f['num'])
            ws.write_number(row, self.COL_NET, float(line.get('net') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_QTY,
                       'TOTALES', f['total_lbl_right'])
        ws.write_number(row, self.COL_COST, float(self.data.get('total_cost') or 0.0), f['total_num'])
        ws.write_number(row, self.COL_PROVISION, float(self.data.get('total_provision') or 0.0), f['total_num'])
        ws.write_number(row, self.COL_NET, float(self.data.get('total_net') or 0.0), f['total_num'])


class InvBal39ReportExcel(InvBalReportBase):
    """Formato 3.9 - Intangibles (cuenta 34).

    Columnas: fecha de inicio de la operacion, descripcion del intangible,
    tipo de intangible (Tabla 7), valor contable, amortizacion contable
    acumulada, valor neto contable.

    `data`: {'lines': [{start_date, description, intangible_type, value,
    amortization, net}], 'total_value', 'total_amortization', 'total_net'}
    """

    FORMATO_CODE = '3.9'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 34 - Intangibles'
    SHEET_NAME = 'F3.9 Intangibles'
    LANDSCAPE = True

    COL_DATE = 0
    COL_DESC = 1
    COL_TYPE = 2
    COL_VALUE = 3
    COL_AMORT = 4
    COL_NET = 5

    def build(self, ws, workbook):
        f = self._formats
        widths = [16, 60, 16, 18, 18, 18]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)

        row = self._write_standard_header(ws, 0, self.COL_NET)

        ws.set_row(row, 44)
        headers = [
            'FECHA DE INICIO DE LA OPERACIÓN', 'DESCRIPCIÓN DEL INTANGIBLE',
            'TIPO DE INTANGIBLE (TABLA 7)', 'VALOR CONTABLE DEL INTANGIBLE',
            'AMORTIZACIÓN CONTABLE ACUMULADA', 'VALOR NETO CONTABLE DEL INTANGIBLE',
        ]
        for col, header in enumerate(headers):
            ws.write(row, col, header, f['col'])
        row += 1

        for line in self.data.get('lines', []):
            self._write_date(ws, row, self.COL_DATE, line.get('start_date'))
            ws.write_string(row, self.COL_DESC, line.get('description') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_TYPE, line.get('intangible_type') or '', f['txt_center'])
            ws.write_number(row, self.COL_VALUE, float(line.get('value') or 0.0), f['num'])
            ws.write_number(row, self.COL_AMORT, float(line.get('amortization') or 0.0), f['num'])
            ws.write_number(row, self.COL_NET, float(line.get('net') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_DATE, row, self.COL_TYPE,
                       'TOTALES', f['total_lbl_right'])
        ws.write_number(row, self.COL_VALUE, float(self.data.get('total_value') or 0.0), f['total_num'])
        ws.write_number(row, self.COL_AMORT, float(self.data.get('total_amortization') or 0.0), f['total_num'])
        ws.write_number(row, self.COL_NET, float(self.data.get('total_net') or 0.0), f['total_num'])


class InvBal310ReportExcel(InvBalReportBase):
    """Formato 3.10 - Tributos por pagar (cuenta 40).

    Columnas: cuenta y subcuenta (codigo, denominacion) | saldo final.

    `data`: {'lines': [{code, name, balance}], 'total'}
    """

    FORMATO_CODE = '3.10'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 40 - Tributos por pagar'
    SHEET_NAME = 'F3.10 Tributos'

    COL_CODE = 0
    COL_NAME = 1
    COL_BALANCE = 2

    def build(self, ws, workbook):
        f = self._formats
        ws.set_column(self.COL_CODE, self.COL_CODE, 14)
        ws.set_column(self.COL_NAME, self.COL_NAME, 70)
        ws.set_column(self.COL_BALANCE, self.COL_BALANCE, 18)

        row = self._write_standard_header(ws, 0, self.COL_BALANCE)

        ws.set_row(row, 22)
        ws.set_row(row + 1, 22)
        ws.merge_range(row, self.COL_CODE, row, self.COL_NAME,
                       'CUENTA Y SUBCUENTA TRIBUTOS POR PAGAR', f['col'])
        ws.merge_range(row, self.COL_BALANCE, row + 1, self.COL_BALANCE,
                       'SALDO FINAL', f['col'])
        ws.write(row + 1, self.COL_CODE, 'CÓDIGO', f['col'])
        ws.write(row + 1, self.COL_NAME, 'DENOMINACIÓN', f['col'])
        row += 2

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_CODE, line.get('code') or '', f['txt'])
            ws.write_string(row, self.COL_NAME, line.get('name') or '', f['txt_wrap'])
            ws.write_number(row, self.COL_BALANCE, float(line.get('balance') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_CODE, row, self.COL_NAME,
                       'TOTAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_BALANCE, float(self.data.get('total') or 0.0), f['total_num'])