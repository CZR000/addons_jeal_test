from .report_inv_bal_base import InvBalReportBase, InvBalPartnerReportBase


class InvBal311ReportExcel(InvBalReportBase):
    """Formato 3.11 - Remuneraciones y participaciones por pagar (cuenta 41).

    Columnas: Cuenta y subcuenta (codigo, denominacion) | Trabajador
    (codigo, apellidos y nombres, documento de identidad tipo Tabla 2 y
    numero) | Saldo final.

    `data`: {'lines': [{account_code, account_name, worker_code,
    worker_name, doc_type, doc_number, balance}], 'total'}
    """

    FORMATO_CODE = '3.11'
    FORMATO_TITLE = ('Detalle del saldo de la cuenta 41 - Remuneraciones y '
                     'participaciones por pagar')
    SHEET_NAME = 'F3.11 Remuneraciones'
    LANDSCAPE = True

    COL_ACC_CODE = 0
    COL_ACC_NAME = 1
    COL_WORKER_CODE = 2
    COL_WORKER_NAME = 3
    COL_DOC_TYPE = 4
    COL_DOC_NUMBER = 5
    COL_BALANCE = 6

    def build(self, ws, workbook):
        f = self._formats
        widths = [12, 40, 15, 40, 12, 15, 16]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)

        row = self._write_standard_header(ws, 0, self.COL_BALANCE)

        ws.set_row(row, 20)
        ws.set_row(row + 1, 20)
        ws.set_row(row + 2, 30)
        ws.merge_range(row, self.COL_ACC_CODE, row, self.COL_ACC_NAME,
                       'CUENTA Y SUBCUENTA REMUNERACIONES POR PAGAR', f['col'])
        ws.merge_range(row, self.COL_WORKER_CODE, row, self.COL_DOC_NUMBER,
                       'TRABAJADOR', f['col'])
        ws.merge_range(row, self.COL_BALANCE, row + 2, self.COL_BALANCE,
                       'SALDO FINAL', f['col'])
        for col, label in ((self.COL_ACC_CODE, 'CÓDIGO'),
                           (self.COL_ACC_NAME, 'DENOMINACIÓN'),
                           (self.COL_WORKER_CODE, 'CÓDIGO'),
                           (self.COL_WORKER_NAME, 'APELLIDOS Y NOMBRES')):
            ws.merge_range(row + 1, col, row + 2, col, label, f['col'])
        ws.merge_range(row + 1, self.COL_DOC_TYPE, row + 1, self.COL_DOC_NUMBER,
                       'DOCUMENTO DE IDENTIDAD', f['col'])
        ws.write(row + 2, self.COL_DOC_TYPE, 'TIPO (TABLA 2)', f['col'])
        ws.write(row + 2, self.COL_DOC_NUMBER, 'NÚMERO', f['col'])
        row += 3

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_ACC_CODE, line.get('account_code') or '', f['txt'])
            ws.write_string(row, self.COL_ACC_NAME, line.get('account_name') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_WORKER_CODE, line.get('worker_code') or '', f['txt'])
            ws.write_string(row, self.COL_WORKER_NAME, line.get('worker_name') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_DOC_TYPE, str(line.get('doc_type') or ''), f['txt_center'])
            ws.write_string(row, self.COL_DOC_NUMBER, line.get('doc_number') or '', f['txt'])
            ws.write_number(row, self.COL_BALANCE, float(line.get('balance') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_ACC_CODE, row, self.COL_DOC_NUMBER,
                       'TOTAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_BALANCE, float(self.data.get('total') or 0.0), f['total_num'])


class InvBal312ReportExcel(InvBalPartnerReportBase):
    """Formato 3.12 - Proveedores (cuenta 42)."""

    FORMATO_CODE = '3.12'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 42 - Proveedores'
    SHEET_NAME = 'F3.12 Proveedores'
    PARTY_LABEL = 'INFORMACIÓN DEL PROVEEDOR'
    AMOUNT_LABEL = 'MONTO DE LA CUENTA POR PAGAR'
    DATE_LABEL = 'FECHA DE EMISIÓN DEL COMPROBANTE DE PAGO'


class InvBal313ReportExcel(InvBalReportBase):
    """Formato 3.13 - Cuentas por pagar diversas (cuentas 46 y 47).

    Columnas: Informacion de terceros (tipo doc Tabla 2, numero, nombre) |
    descripcion de la obligacion | fecha de emision del comprobante o de
    inicio de la operacion | monto pendiente de pago.

    `data`: {'lines': [{doc_type, doc_number, name, doc_ref, date,
    amount}], 'total'}
    """

    FORMATO_CODE = '3.13'
    FORMATO_TITLE = ('Detalle del saldo de la cuenta 46 - Cuentas por pagar '
                     'diversas - Terceros y relacionadas')
    SHEET_NAME = 'F3.13 CxP Diversas'
    LANDSCAPE = True

    COL_DOC_TYPE = 0
    COL_DOC_NUMBER = 1
    COL_NAME = 2
    COL_DESC = 3
    COL_DATE = 4
    COL_AMOUNT = 5

    def build(self, ws, workbook):
        f = self._formats
        widths = [14, 16, 42, 34, 22, 18]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)

        row = self._write_standard_header(ws, 0, self.COL_AMOUNT)

        ws.set_row(row, 20)
        ws.set_row(row + 1, 20)
        ws.set_row(row + 2, 62)
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_NAME,
                       'INFORMACIÓN DE TERCEROS', f['col'])
        ws.merge_range(row, self.COL_DESC, row + 2, self.COL_DESC,
                       'DESCRIPCIÓN DE LA OBLIGACIÓN', f['col'])
        ws.merge_range(row, self.COL_DATE, row + 2, self.COL_DATE,
                       'FECHA DE EMISIÓN DEL COMPROBANTE DE PAGO O FECHA DE '
                       'INICIO DE LA OPERACIÓN', f['col'])
        ws.merge_range(row, self.COL_AMOUNT, row + 2, self.COL_AMOUNT,
                       'MONTO PENDIENTE DE PAGO', f['col'])
        ws.merge_range(row + 1, self.COL_DOC_TYPE, row + 1, self.COL_DOC_NUMBER,
                       'DOCUMENTO DE IDENTIDAD', f['col'])
        ws.merge_range(row + 1, self.COL_NAME, row + 2, self.COL_NAME,
                       'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL', f['col'])
        ws.write(row + 2, self.COL_DOC_TYPE, 'TIPO (TABLA 2)', f['col'])
        ws.write(row + 2, self.COL_DOC_NUMBER, 'NÚMERO', f['col'])
        row += 3

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_DOC_TYPE, str(line.get('doc_type') or ''), f['txt_center'])
            ws.write_string(row, self.COL_DOC_NUMBER, line.get('doc_number') or '', f['txt'])
            ws.write_string(row, self.COL_NAME, line.get('name') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_DESC, line.get('doc_ref') or '', f['txt_wrap'])
            self._write_date(ws, row, self.COL_DATE, line.get('date'))
            ws.write_number(row, self.COL_AMOUNT, float(line.get('amount') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_DATE,
                       'SALDO TOTAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_AMOUNT, float(self.data.get('total') or 0.0), f['total_num'])