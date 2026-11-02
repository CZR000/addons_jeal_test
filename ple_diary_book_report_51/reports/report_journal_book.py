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


class JournalBookReportExcel(object):
    """Genera el Excel del PLE Libro Diario Formato 5.1 con el layout
    visual: cabecera de identificacion (5 filas) + tabla con doble fila
    de encabezado con grupos fusionados (Referencia Operacion, Cuenta
    Contable Asociada, Movimientos) + detalle de asientos + totales.
    """

    def __init__(self, obj, data):
        self.obj = obj
        self.data = data

    # ------------------------------------------------------------------
    # Helpers de cabecera
    # ------------------------------------------------------------------
    def _period_label(self):
        d = self.obj.date_start
        if not d:
            return ''
        return '%s DE %d' % (MONTHS_ES.get(d.month, ''), d.year)

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
        ws = workbook.add_worksheet('Libro Diario 5.1')

        # --- Configuracion de impresion (para la conversion a PDF) ---
        ws.set_landscape()
        ws.set_paper(9)                        # 9 = A4
        ws.set_margins(0.2, 0.2, 0.3, 0.3)     # left, right, top, bottom (pulgadas)
        ws.fit_to_pages(1, 0)                  # 1 pagina de ancho, alto libre
        ws.repeat_rows(0, 7)                    # repite las 8 filas de cabecera

        # -------- Formatos --------
        fmt_hdr_lbl = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
        })
        fmt_hdr_val = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter',
        })
    
        fmt_group = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#D9E1F2',
        })
        fmt_col = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#D9E1F2',
            'text_wrap': True,
        })
    
        fmt_txt = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
        })
        fmt_txt_center = workbook.add_format({
            'size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter',
        })
        fmt_date = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': 'dd/mm/yy',
        })
        fmt_num = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': '#,##0.00',
        })
    
        fmt_total_lbl = workbook.add_format({
            'bold': True, 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#F2F2F2',
        })
        fmt_total_num = workbook.add_format({
            'bold': True, 'border': 1, 'size': 10, 'valign': 'vcenter',
            'num_format': '#,##0.00', 'bg_color': '#F2F2F2',
        })
    
        # -------- Anchos de columnas --------
        ws.set_column('A:A', 15)   # CUO
        ws.set_column('B:B', 12)   # FECHA
        ws.set_column('C:C', 35)   # DESCRIPCION
        ws.set_column('D:D', 6)    # CL
        ws.set_column('E:E', 12)   # CORRELATIVO
        ws.set_column('F:F', 18)   # N° DOC
        ws.set_column('G:G', 10)   # CODIGO
        ws.set_column('H:H', 40)   # DENOMINACION
        ws.set_column('I:I', 15)   # ANEXO
        ws.set_column('J:J', 15)   # DEBE
        ws.set_column('K:K', 15)   # HABER
    
        # -------- Cabecera del reporte (filas 1..5) --------
        company = self.obj.company_id
        ws.write('A1', 'Formato 5.1', fmt_hdr_lbl)
        ws.write('B1', 'Libro Diario', fmt_hdr_val)
        ws.write('A2', 'Periodo', fmt_hdr_lbl)
        ws.write('B2', self._period_label(), fmt_hdr_val)
        ws.write('A3', 'RUC', fmt_hdr_lbl)
        ws.write('B3', company.vat or '', fmt_hdr_val)
        ws.write('A4', 'Razon Social', fmt_hdr_lbl)
        ws.write('B4', company.name or '', fmt_hdr_val)
        ws.write('A5', 'Expresado en', fmt_hdr_lbl)
        ws.write('B5', self._currency_label(), fmt_hdr_val)
        # Fila 6 en blanco
    
        # -------- Encabezado de tabla (filas 7 y 8) --------
        ws.set_row(6, 22)
        ws.set_row(7, 32)
    
        ws.merge_range('A7:A8',
                       'NUMERO CORRELATIVO O CODIGO UNICO DE OPERACION (CUO)',
                       fmt_col)
        ws.merge_range('B7:B8', 'FECHA OPERACION', fmt_col)
        ws.merge_range('C7:C8', 'DESCRIPCION OPERACION', fmt_col)
        ws.merge_range('D7:F7', 'REFERENCIA OPERACION', fmt_group)
        ws.merge_range('G7:H7', 'CUENTA CONTABLE ASOCIADA', fmt_group)
        ws.merge_range('I7:I8', 'ANEXO', fmt_col)
        ws.merge_range('J7:K7', 'MOVIMIENTOS', fmt_group)
    
        ws.write('D8', 'CL', fmt_col)
        ws.write('E8', 'CORRELATIVO', fmt_col)
        ws.write('F8', 'N° DOCUMENTO', fmt_col)
        ws.write('G8', 'CODIGO', fmt_col)
        ws.write('H8', 'DENOMINACION', fmt_col)
        ws.write('J8', 'DEBE', fmt_col)
        ws.write('K8', 'HABER', fmt_col)
    
        # -------- Detalle (fila 9 en adelante) --------
        row = 8
        total_debit = 0.0
        total_credit = 0.0
    
        for r in self.data:
            ws.write(row, 0, r.get('cuo') or '', fmt_txt_center)
    
            fecha = r.get('fecha_operacion')
            if isinstance(fecha, (date, datetime)):
                ws.write_datetime(row, 1, fecha, fmt_date)
            else:
                ws.write(row, 1, fecha or '', fmt_txt)
    
            ws.write(row, 2, (r.get('descripcion') or '')[:200], fmt_txt)
            ws.write(row, 3, r.get('cl') or '', fmt_txt_center)
            ws.write(row, 4, r.get('correlativo') or '', fmt_txt_center)
            ws.write(row, 5, r.get('nro_documento') or '', fmt_txt)
            ws.write(row, 6, r.get('codigo') or '', fmt_txt)
            ws.write(row, 7, r.get('denominacion') or '', fmt_txt)
            ws.write(row, 8, r.get('anexo') or '', fmt_txt)
    
            debit = float(r.get('debit') or 0.0)
            credit = float(r.get('credit') or 0.0)
            ws.write_number(row, 9, debit, fmt_num)
            ws.write_number(row, 10, credit, fmt_num)
    
            total_debit += debit
            total_credit += credit
            row += 1
    
        # -------- Totales --------
        ws.merge_range(row, 0, row, 8, 'TOTALES', fmt_total_lbl)
        ws.write_number(row, 9, total_debit, fmt_total_num)
        ws.write_number(row, 10, total_credit, fmt_total_num)
    
        # Congelar la cabecera de la tabla
        ws.freeze_panes(8, 0)
    
        workbook.close()
        output.seek(0)
        return output.read()

    def get_filename(self):
        company = self.obj.company_id
        period = self.obj.date_start.strftime('%Y%m') if self.obj.date_start else ''
        safe_name = ''.join(
            c if c.isalnum() else '_' for c in (company.name or 'company')
        )
        return 'Libro_Diario_5.1_%s_%s.xlsx' % (safe_name, period)