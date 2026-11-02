from .report_inv_bal_base import InvBalReportBase, InvBalPartnerReportBase


class InvBal35ReportExcel(InvBalPartnerReportBase):
    """Formato 3.5 - Cuentas por cobrar diversas (cuenta 16)."""

    FORMATO_CODE = '3.5'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 16 - Cuentas por cobrar diversas'
    SHEET_NAME = 'F3.5 CxC Diversas'
    PARTY_LABEL = 'INFORMACIÓN DE TERCEROS'
    AMOUNT_LABEL = 'MONTO DE LA CUENTA POR COBRAR'
    DATE_LABEL = ('FECHA DE EMISIÓN DEL COMPROBANTE DE PAGO O FECHA DE INICIO '
                  'DE LA OPERACIÓN')


class InvBal36ReportExcel(InvBalReportBase):
    """Formato 3.6 - Estimacion de cuentas de cobranza dudosa (cuenta 19).

    Columnas: Informacion de deudores (tipo doc Tabla 2, numero, nombre) |
    Cuenta por cobrar provisionada (numero del documento, fecha de emision
    o de inicio de la operacion, monto).

    `data`: {'lines': [{doc_type, doc_number, name, doc_ref, date,
    amount}], 'total'}
    """

    FORMATO_CODE = '3.6'
    FORMATO_TITLE = ('Detalle del saldo de la cuenta 19 - Estimación de cuentas '
                     'de cobranza dudosa')
    SHEET_NAME = 'F3.6 Cobranza Dudosa'
    LANDSCAPE = True

    COL_DOC_TYPE = 0
    COL_DOC_NUMBER = 1
    COL_NAME = 2
    COL_DOC_REF = 3
    COL_DATE = 4
    COL_AMOUNT = 5

    def build(self, ws, workbook):
        f = self._formats
        ws.set_column(self.COL_DOC_TYPE, self.COL_DOC_TYPE, 14)
        ws.set_column(self.COL_DOC_NUMBER, self.COL_DOC_NUMBER, 16)
        ws.set_column(self.COL_NAME, self.COL_NAME, 45)
        ws.set_column(self.COL_DOC_REF, self.COL_DOC_REF, 26)
        ws.set_column(self.COL_DATE, self.COL_DATE, 22)
        ws.set_column(self.COL_AMOUNT, self.COL_AMOUNT, 18)

        row = self._write_standard_header(ws, 0, self.COL_AMOUNT)

        ws.set_row(row, 20)
        ws.set_row(row + 1, 20)
        ws.set_row(row + 2, 62)
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_NAME,
                       'INFORMACIÓN DE DEUDORES', f['col'])
        ws.merge_range(row, self.COL_DOC_REF, row + 1, self.COL_AMOUNT,
                       'CUENTA POR COBRAR PROVISIONADA', f['col'])
        ws.merge_range(row + 1, self.COL_DOC_TYPE, row + 1, self.COL_DOC_NUMBER,
                       'DOCUMENTO DE IDENTIDAD', f['col'])
        ws.merge_range(row + 1, self.COL_NAME, row + 2, self.COL_NAME,
                       'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL', f['col'])
        ws.write(row + 2, self.COL_DOC_TYPE, 'TIPO (TABLA 2)', f['col'])
        ws.write(row + 2, self.COL_DOC_NUMBER, 'NÚMERO', f['col'])
        ws.write(row + 2, self.COL_DOC_REF, 'NÚMERO DEL DOCUMENTO', f['col'])
        ws.write(row + 2, self.COL_DATE,
                 'FECHA DE EMISIÓN DEL COMPROBANTE DE PAGO O FECHA DE INICIO '
                 'DE LA OPERACIÓN', f['col'])
        ws.write(row + 2, self.COL_AMOUNT, 'MONTO', f['col'])
        row += 3

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_DOC_TYPE, str(line.get('doc_type') or ''), f['txt_center'])
            ws.write_string(row, self.COL_DOC_NUMBER, line.get('doc_number') or '', f['txt'])
            ws.write_string(row, self.COL_NAME, line.get('name') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_DOC_REF, line.get('doc_ref') or '', f['txt_wrap'])
            self._write_date(ws, row, self.COL_DATE, line.get('date'))
            ws.write_number(row, self.COL_AMOUNT, float(line.get('amount') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_DATE,
                       'MONTO TOTAL PROVISIONADO', f['total_lbl_right'])
        ws.write_number(row, self.COL_AMOUNT,
                        float(self.data.get('total') or 0.0), f['total_num'])


class InvBal37ReportExcel(InvBalReportBase):
    """Formato 3.7 - Mercaderias y productos terminados (cuentas 20 y 21).

    Columnas: codigo de la existencia, tipo de existencia (Tabla 5),
    descripcion, codigo de unidad de medida (Tabla 6), cantidad, costo
    unitario, costo total. En la cabecera se indica el metodo de
    evaluacion aplicado.

    `data`: {'lines': [{code, existence_type, description, uom_code,
    quantity, unit_cost, total_cost}], 'total', 'method'}
    """

    FORMATO_CODE = '3.7'
    FORMATO_TITLE = ('Detalle del saldo de la cuenta 20 - Mercaderías y la cuenta '
                     '21 - Productos terminados')
    SHEET_NAME = 'F3.7 Existencias'
    LANDSCAPE = True

    COL_CODE = 0
    COL_TYPE = 1
    COL_DESC = 2
    COL_UOM = 3
    COL_QTY = 4
    COL_UNIT = 5
    COL_TOTAL = 6

    def build(self, ws, workbook):
        f = self._formats
        f['qty'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': '#,##0.00;-#,##0.00;"-"',
        })
        f['unit'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': '#,##0.00;-#,##0.00;"-"',
        })

        ws.set_column(self.COL_CODE, self.COL_CODE, 16)
        ws.set_column(self.COL_TYPE, self.COL_TYPE, 13)
        ws.set_column(self.COL_DESC, self.COL_DESC, 50)
        ws.set_column(self.COL_UOM, self.COL_UOM, 14)
        ws.set_column(self.COL_QTY, self.COL_QTY, 14)
        ws.set_column(self.COL_UNIT, self.COL_UNIT, 16)
        ws.set_column(self.COL_TOTAL, self.COL_TOTAL, 18)

        row = self._write_standard_header(ws, 0, self.COL_TOTAL)
        # Metodo de evaluacion, debajo de la razon social
        ws.write_rich_string(
            row - 1, 0,
            f['hdr_lbl'], 'MÉTODO DE VALUACIÓN APLICADO:  ',
            f['hdr_val'], self.data.get('method') or '-',
        )
        row += 1

        ws.set_row(row, 44)
        headers = [
            'CÓDIGO DE LA EXISTENCIA', 'TIPO DE EXISTENCIA (TABLA 5)',
            'DESCRIPCIÓN', 'CÓDIGO DE LA UNIDAD DE MEDIDA (TABLA 6)',
            'CANTIDAD', 'COSTO UNITARIO', 'COSTO TOTAL',
        ]
        for col, header in enumerate(headers):
            ws.write(row, col, header, f['col'])
        row += 1

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_CODE, line.get('code') or '', f['txt'])
            ws.write_string(row, self.COL_TYPE, line.get('existence_type') or '', f['txt_center'])
            ws.write_string(row, self.COL_DESC, line.get('description') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_UOM, line.get('uom_code') or '', f['txt_center'])
            ws.write_number(row, self.COL_QTY, float(line.get('quantity') or 0.0), f['qty'])
            ws.write_number(row, self.COL_UNIT, float(line.get('unit_cost') or 0.0), f['unit'])
            ws.write_number(row, self.COL_TOTAL, float(line.get('total_cost') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_CODE, row, self.COL_UNIT,
                       'COSTO TOTAL GENERAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_TOTAL,
                        float(self.data.get('total') or 0.0), f['total_num'])