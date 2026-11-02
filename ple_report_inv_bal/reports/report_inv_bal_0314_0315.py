from .report_inv_bal_base import InvBalReportBase


class InvBal314ReportExcel(InvBalReportBase):
    """Formato 3.14 - Beneficios sociales de los trabajadores (cuenta 47).

    Columnas: documento de identidad (tipo Tabla 2, numero), apellidos y
    nombres del trabajador, saldo final.

    `data`: {'lines': [{doc_type, doc_number, name, balance}], 'total'}
    """

    FORMATO_CODE = '3.14'
    FORMATO_TITLE = ('Detalle del saldo de la cuenta 47 - Beneficios sociales '
                     'de los trabajadores')
    SHEET_NAME = 'F3.14 Beneficios Sociales'

    COL_DOC_TYPE = 0
    COL_DOC_NUMBER = 1
    COL_NAME = 2
    COL_BALANCE = 3

    def build(self, ws, workbook):
        f = self._formats
        widths = [14, 16, 60, 18]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)

        row = self._write_standard_header(ws, 0, self.COL_BALANCE)

        ws.set_row(row, 22)
        ws.set_row(row + 1, 22)
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_DOC_NUMBER,
                       'DOCUMENTO DE IDENTIDAD', f['col'])
        ws.merge_range(row, self.COL_NAME, row + 1, self.COL_NAME,
                       'APELLIDOS Y NOMBRES DEL TRABAJADOR', f['col'])
        ws.merge_range(row, self.COL_BALANCE, row + 1, self.COL_BALANCE,
                       'SALDO FINAL', f['col'])
        ws.write(row + 1, self.COL_DOC_TYPE, 'TIPO (TABLA 2)', f['col'])
        ws.write(row + 1, self.COL_DOC_NUMBER, 'NÚMERO', f['col'])
        row += 2

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_DOC_TYPE, str(line.get('doc_type') or ''), f['txt_center'])
            ws.write_string(row, self.COL_DOC_NUMBER, line.get('doc_number') or '', f['txt'])
            ws.write_string(row, self.COL_NAME, line.get('name') or '', f['txt_wrap'])
            ws.write_number(row, self.COL_BALANCE, float(line.get('balance') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_NAME,
                       'TOTAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_BALANCE, float(self.data.get('total') or 0.0), f['total_num'])


class InvBal315ReportExcel(InvBalReportBase):
    """Formato 3.15 - Ganancias diferidas (cuenta 49).

    Columnas: concepto, numero de comprobante de pago relacionado, saldo
    final.

    `data`: {'lines': [{concept, doc_ref, balance}], 'total'}
    """

    FORMATO_CODE = '3.15'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 49 - Ganancias diferidas'
    SHEET_NAME = 'F3.15 Ganancias Diferidas'

    COL_CONCEPT = 0
    COL_DOC_REF = 1
    COL_BALANCE = 2

    def build(self, ws, workbook):
        f = self._formats
        ws.set_column(self.COL_CONCEPT, self.COL_CONCEPT, 65)
        ws.set_column(self.COL_DOC_REF, self.COL_DOC_REF, 24)
        ws.set_column(self.COL_BALANCE, self.COL_BALANCE, 18)

        row = self._write_standard_header(ws, 0, self.COL_BALANCE)

        ws.set_row(row, 36)
        headers = ['CONCEPTO', 'NÚMERO DE COMPROBANTE DE PAGO RELACIONADO', 'SALDO FINAL']
        for col, header in enumerate(headers):
            ws.write(row, col, header, f['col'])
        row += 1

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_CONCEPT, line.get('concept') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_DOC_REF, line.get('doc_ref') or '', f['txt_center'])
            ws.write_number(row, self.COL_BALANCE, float(line.get('balance') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_CONCEPT, row, self.COL_DOC_REF,
                       'TOTAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_BALANCE, float(self.data.get('total') or 0.0), f['total_num'])
