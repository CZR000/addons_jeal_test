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
COL_FECHA = 0     # A
COL_TIPO = 1      # B - Tipo Tabla 10
COL_SERIE = 2     # C
COL_NUMERO = 3    # D
COL_OP_TYPE = 4   # E - Tipo Operacion Tabla 12
COL_ENTRADAS = 5  # F
COL_SALIDAS = 6   # G
COL_SALDO = 7     # H

LAST_COL = COL_SALDO


class StockPermanentInventoryReportExcel(object):
    """Genera el Excel del PLE Registro Inventario Permanente 12.1.

    Layout:
      - Cabecera comun por MES (7 filas: Formato + Periodo + RUC +
        Razon Social + Establecimiento).
      - Por cada producto en el mes:
          * bloque de metadatos de producto (4 filas: codigo existencia,
            tipo T5, descripcion, codigo UM T6)
          * encabezado de tabla (2 filas con merges)
          * fila SALDO INICIAL
          * una fila por movimiento
    """

    def __init__(self, obj, data):
        self.obj = obj
        self.data = data
        self._formats = {}

    # ------------------------------------------------------------------
    # Generacion
    # ------------------------------------------------------------------
    def get_content(self):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = workbook.add_worksheet('Registro Inventario 12.1')

        ws.set_landscape()
        ws.set_paper(9)                        # 9 = A4
        ws.set_margins(0.2, 0.2, 0.3, 0.3)     # left, right, top, bottom
        ws.fit_to_pages(1, 0)                  # 8 columnas: entra comodo
        
        self._register_formats(workbook)
        self._set_columns(ws)

        row = 0
        for month_block in self.data:
            row = self._write_month_header(ws, row, month_block['label'])
            for product_block in month_block['products']:
                row = self._write_product_block(ws, row, product_block)
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
        return 'Registro_Inventario_12.1_%s_%s.xlsx' % (safe_name, period)

    # ------------------------------------------------------------------
    # Formatos y anchos
    # ------------------------------------------------------------------
    def _register_formats(self, workbook):
        f = self._formats

        f['title'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
            'text_wrap': True,
        })
        f['hdr_lbl'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
        })
        f['hdr_val'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter',
            'underline': 1,
        })

        f['group'] = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#D9E1F2',
            'text_wrap': True,
        })
        f['col'] = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#D9E1F2',
            'text_wrap': True,
        })

        f['txt'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
        })
        f['txt_center'] = workbook.add_format({
            'size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter',
        })
        f['date'] = workbook.add_format({
            'size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter',
            'num_format': 'dd/mm/yyyy',
        })
        f['qty'] = workbook.add_format({
            'size': 10, 'border': 1, 'align': 'right', 'valign': 'vcenter',
            'num_format': '#,##0.00',
        })

        f['saldo_ini_lbl'] = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#F2F2F2',
        })
        f['saldo_ini_center'] = workbook.add_format({
            'bold': True, 'size': 10, 'border': 1, 'align': 'center',
            'valign': 'vcenter', 'bg_color': '#F2F2F2',
        })
        f['saldo_ini_qty'] = workbook.add_format({
            'bold': True, 'size': 10, 'border': 1, 'align': 'right',
            'valign': 'vcenter', 'num_format': '#,##0.00',
            'bg_color': '#F2F2F2',
        })

    def _set_columns(self, ws):
        ws.set_column(COL_FECHA,    COL_FECHA,    12)
        ws.set_column(COL_TIPO,     COL_TIPO,     14)
        ws.set_column(COL_SERIE,    COL_SERIE,    10)
        ws.set_column(COL_NUMERO,   COL_NUMERO,   20)
        ws.set_column(COL_OP_TYPE,  COL_OP_TYPE,  14)
        ws.set_column(COL_ENTRADAS, COL_ENTRADAS, 14)
        ws.set_column(COL_SALIDAS,  COL_SALIDAS,  14)
        ws.set_column(COL_SALDO,    COL_SALDO,    14)

    # ------------------------------------------------------------------
    # Bloques
    # ------------------------------------------------------------------
    def _write_month_header(self, ws, row, period_label):
        """Escribe la cabecera comun del mes (filas 1-7 de la imagen)."""
        company = self.obj.company_id
        f = self._formats

        # Titulo (2 filas mergeadas)
        ws.merge_range(
            row, 0, row + 1, LAST_COL,
            'FORMATO 12.1: "REGISTRO DEL INVENTARIO PERMANENTE EN UNIDADES '
            'FISICAS - DETALLE DEL INVENTARIO PERMANENTE EN UNIDADES FISICAS"',
            f['title'],
        )
        ws.set_row(row,     18)
        ws.set_row(row + 1, 18)
        row += 2

        # Fila vacia
        row += 1

        # PERIODO
        ws.write(row, 0, 'PERIODO:', f['hdr_lbl'])
        ws.write(row, 1, period_label, f['hdr_val'])
        row += 1

        # RUC
        ws.write(row, 0, 'RUC:', f['hdr_lbl'])
        ws.write(row, 1, company.vat or '', f['hdr_val'])
        row += 1

        # RAZON SOCIAL
        ws.write(row, 0,
                 'APELLIDOS Y NOMBRES, DENOMINACION O RAZON SOCIAL:',
                 f['hdr_lbl'])
        ws.write(row, 3, company.name or '', f['hdr_val'])
        row += 1

        # ESTABLECIMIENTO
        ws.write(row, 0, 'ESTABLECIMIENTO (1):', f['hdr_lbl'])
        ws.write(row, 1,
                 getattr(self.obj, '_establishment_code',
                         None) or '0000',
                 f['hdr_val'])
        row += 1

        # Fila vacia
        row += 1

        return row

    def _write_product_block(self, ws, row, product_block):
        """Escribe el bloque de un producto: metadatos + tabla + saldo
        inicial + movimientos."""
        f = self._formats

        # Metadatos del producto (4 filas)
        ws.write(row, 0, 'CODIGO DE LA EXISTENCIA:', f['hdr_lbl'])
        ws.write(row, 1, product_block['product_code'], f['hdr_val'])
        row += 1

        ws.write(row, 0, 'TIPO (TABLA 5):', f['hdr_lbl'])
        ws.write(row, 1, product_block['existence_type'] or '', f['hdr_val'])
        row += 1

        ws.write(row, 0, 'DESCRIPCION:', f['hdr_lbl'])
        ws.write(row, 1, product_block['product_name'], f['hdr_val'])
        row += 1

        ws.write(row, 0,
                 'CODIGO DE LA UNIDAD DE MEDIDA (TABLA 6):',
                 f['hdr_lbl'])
        ws.write(row, 1, product_block['uom_code'], f['hdr_val'])
        row += 1

        # Fila vacia
        row += 1

        # Encabezado de tabla (2 filas con merges)
        row = self._write_table_header(ws, row)

        # Fila SALDO INICIAL
        row = self._write_saldo_inicial_row(ws, row,
                                            product_block['saldo_inicial'])

        # Filas de movimientos
        for line in product_block['lines']:
            row = self._write_movement_row(ws, row, line)

        # Separador entre productos
        row += 1

        return row

    def _write_table_header(self, ws, row):
        f = self._formats
        ws.set_row(row,     30)
        ws.set_row(row + 1, 30)

        # Header agrupado: A:D "DOCUMENTO DE TRASLADO..."
        ws.merge_range(row, COL_FECHA, row, COL_NUMERO,
                       'DOCUMENTO DE TRASLADO, COMPROBANTE DE PAGO, '
                       'DOCUMENTO INTERNO O SIMILAR',
                       f['group'])

        # Merges verticales para las columnas simples
        ws.merge_range(row, COL_OP_TYPE, row + 1, COL_OP_TYPE,
                       'TIPO DE OPERACION\n(TABLA 12)', f['group'])
        ws.merge_range(row, COL_ENTRADAS, row + 1, COL_ENTRADAS,
                       'ENTRADAS', f['group'])
        ws.merge_range(row, COL_SALIDAS, row + 1, COL_SALIDAS,
                       'SALIDAS', f['group'])
        ws.merge_range(row, COL_SALDO, row + 1, COL_SALDO,
                       'SALDO FINAL', f['group'])

        # Segunda fila: sub-headers del grupo A:D
        ws.write(row + 1, COL_FECHA,  'FECHA',          f['col'])
        ws.write(row + 1, COL_TIPO,   'TIPO (TABLA 10)', f['col'])
        ws.write(row + 1, COL_SERIE,  'SERIE',          f['col'])
        ws.write(row + 1, COL_NUMERO, 'NUMERO',         f['col'])

        return row + 2

    def _write_saldo_inicial_row(self, ws, row, saldo_inicial):
        f = self._formats

        # A:C vacio bordeado
        for c in [COL_FECHA, COL_TIPO, COL_SERIE]:
            ws.write(row, c, '', f['saldo_ini_lbl'])
        # D: "SALDO INICIAL"
        ws.write(row, COL_NUMERO, 'SALDO INICIAL', f['saldo_ini_center'])
        # E: 16
        ws.write(row, COL_OP_TYPE, '16', f['saldo_ini_center'])
        # F, G: 0
        ws.write_number(row, COL_ENTRADAS, 0.0, f['saldo_ini_qty'])
        ws.write_number(row, COL_SALIDAS,  0.0, f['saldo_ini_qty'])
        # H: saldo inicial
        ws.write_number(row, COL_SALDO, float(saldo_inicial or 0.0),
                        f['saldo_ini_qty'])

        return row + 1

    def _write_movement_row(self, ws, row, line):
        f = self._formats

        fecha = line.get('fecha')
        if isinstance(fecha, (date, datetime)):
            ws.write_datetime(row, COL_FECHA, fecha, f['date'])
        else:
            ws.write(row, COL_FECHA, fecha or '', f['txt_center'])

        ws.write(row, COL_TIPO,    line.get('td') or '',       f['txt_center'])
        ws.write(row, COL_SERIE,   line.get('serie') or '',    f['txt'])
        ws.write(row, COL_NUMERO,  line.get('numero') or '',   f['txt'])
        ws.write(row, COL_OP_TYPE, line.get('op_type') or '',  f['txt_center'])

        ws.write_number(row, COL_ENTRADAS,
                        float(line.get('entrada') or 0.0), f['qty'])
        ws.write_number(row, COL_SALIDAS,
                        float(line.get('salida') or 0.0),  f['qty'])
        ws.write_number(row, COL_SALDO,
                        float(line.get('saldo') or 0.0),   f['qty'])

        return row + 1
