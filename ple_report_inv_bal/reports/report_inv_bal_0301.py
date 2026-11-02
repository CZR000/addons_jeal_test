from .report_inv_bal_base import InvBalReportBase


class InvBal31ReportExcel(InvBalReportBase):
    """Formato 3.1 - Balance General.

    Layout de dos columnas: ACTIVO (izquierda) y PASIVO Y PATRIMONIO
    (derecha), cada una con secciones, lineas y totales, al cierre del
    periodo (date_end).

    `data` es el dict devuelto por _get_data_01():
        {'activo': [(tipo, label, valor), ...],
         'pasivo': [(tipo, label, valor), ...]}
    """

    FORMATO_CODE = '3.1'
    FORMATO_TITLE = 'Balance General'
    SHEET_NAME = 'F3.1 Balance General'

    # Columnas: A..C ACTIVO (label + valor), E..G PASIVO Y PATRIMONIO
    COL_ACT_LBL = 0      # A-B label activo
    COL_ACT_VAL = 2      # C valor activo
    COL_SEP = 3          # D separador
    COL_PAS_LBL = 4      # E-F label pasivo
    COL_PAS_VAL = 6      # G valor pasivo

    def build(self, ws, workbook):
        self._set_columns(ws)
        row = self._write_standard_header(ws, 0, self.COL_PAS_VAL)
        row = self._write_period_banner(ws, row)

        start = row
        self._write_column(ws, start, self.COL_ACT_LBL, self.COL_ACT_VAL,
                           self.data.get('activo', []))
        self._write_column(ws, start, self.COL_PAS_LBL, self.COL_PAS_VAL,
                           self.data.get('pasivo', []))

    def _set_columns(self, ws):
        ws.set_column(0, 0, 4)    # A sangria
        ws.set_column(1, 1, 42)   # B label activo
        ws.set_column(2, 2, 18)   # C valor activo
        ws.set_column(3, 3, 3)    # D separador
        ws.set_column(4, 4, 4)    # E sangria
        ws.set_column(5, 5, 42)   # F label pasivo
        ws.set_column(6, 6, 18)   # G valor pasivo

    def _write_period_banner(self, ws, row):
        f = self._formats
        label = 'Al %s' % (
            self.obj.date_end.strftime('%d/%m/%Y') if self.obj.date_end else ''
        )
        ws.merge_range(row, self.COL_ACT_LBL, row, self.COL_PAS_VAL,
                       'ESTADO DE SITUACION FINANCIERA  -  %s' % label, f['col'])
        return row + 1

    def _write_column(self, ws, start_row, col_lbl, col_val, rows):
        f = self._formats
        row = start_row
        for kind, label, value in rows:
            if kind == 'blank':
                ws.write_blank(row, col_lbl, None, f['blank'])
                ws.write_blank(row, col_lbl + 1, None, f['blank'])
                ws.write_blank(row, col_val, None, f['blank'])
                row += 1
                continue

            if kind == 'section':
                ws.merge_range(row, col_lbl, row, col_val, label, f['section'])
                row += 1
                continue

            lbl_fmt = f['total_lbl'] if kind == 'total' else f['line_lbl']
            num_fmt = f['total_num'] if kind == 'total' else f['num']
            ws.merge_range(row, col_lbl, row, col_val - 1, label, lbl_fmt)
            ws.write_number(row, col_val, float(value or 0.0), num_fmt)
            row += 1
        return row
