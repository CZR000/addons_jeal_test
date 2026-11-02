from odoo import _, fields, models


class InternalTransfersXlsx(models.AbstractModel):
    _name = "report.detail_report_internal_transfers.transfer_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte XLSX de Transferencias"

    def generate_xlsx_report(self, workbook, data, wizards):
        form_data = data.get("form_data", [])

        worksheet = workbook.add_worksheet("REPORTE DE TRANSFERENCIAS")

        # Configuraciones de página y visualización
        worksheet.set_column("A:A", 8)  # Fila más angosta
        worksheet.set_column("B:Y", 22)  # Ancho estándar optimizado
        worksheet.set_row(0, 35)  # Título principal
        for row in range(1, 3):  # Filas de sub-títulos y cabeceras
            worksheet.set_row(row, 20)

        # -------------------------------------------------------------------------
        # ESTILOS
        # -------------------------------------------------------------------------
        base_format = {
            "font_name": "Arial",
            "font_size": 10,
            "border": 1,
            "valign": "vcenter",
        }

        style_title = workbook.add_format(
            {
                **base_format,
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#684C60",
                "align": "center",
                "font_size": 14,
            }
        )
        style_head = workbook.add_format(
            {
                **base_format,
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#684C60",
                "align": "center",
            }
        )
        style_body = workbook.add_format(
            {**base_format, "font_color": "#000000", "align": "left"}
        )
        style_number = workbook.add_format(
            {
                **base_format,
                "font_color": "#000000",
                "align": "right",
                "num_format": "#,##0.00",
            }
        )
        style_date = workbook.add_format(
            {
                **base_format,
                "font_color": "#000000",
                "align": "center",
                "num_format": "dd/mm/yyyy",
            }
        )

        # -------------------------------------------------------------------------
        # CABECERAS
        # -------------------------------------------------------------------------
        worksheet.merge_range(
            "A1:N1", "REPORTE DETALLADO DE TRANSFERENCIAS INTERNAS", style_title
        )
        worksheet.merge_range("O1:U1", "INFORMACIÓN DE ÚLTIMA COMPRA", style_title)

        worksheet.write("A2", "Fecha consultada:", style_head)
        worksheet.write("C2", "Del:", style_head)

        # Validamos fechas
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        if start_date:
            worksheet.write_datetime("D2", fields.Date.to_date(start_date), style_date)
        if end_date:
            worksheet.write("E2", "Hasta:", style_head)
            worksheet.write_datetime("F2", fields.Date.to_date(end_date), style_date)

        headers = [
            "FILA",
            "COMPAÑÍA",
            "CONTACTO",
            "TRANSFERENCIA",
            "TIPO DE OPERACIÓN",
            "FECHA EFECTIVA",
            "DOCUMENTO ORIGEN",
            "DE",
            "PARA",
            "ESTADO",
            "CATEGORÍA DEL PRODUCTO",
            "PRODUCTO",
            "REALIZADO",
            "UNIDAD DE MEDIDA",
            "REFERENCIA DEL PEDIDO",
            "FECHA CONFIRMACIÓN",
            "PROVEEDOR",
            "CANTIDAD TOTAL",
            "PRECIO UNITARIO",
            "IMPUESTOS",
            "MONEDA",
        ]

        for col_num, header in enumerate(headers):
            worksheet.write(2, col_num, header, style_head)

        # -------------------------------------------------------------------------
        # DATOS
        # -------------------------------------------------------------------------
        row = 3
        for idx, line in enumerate(form_data, start=1):
            worksheet.write(row, 0, idx, style_body)
            worksheet.write(row, 1, line.get("compania", ""), style_body)
            worksheet.write(row, 2, line.get("contacto", ""), style_body)
            worksheet.write(row, 3, line.get("referencia", ""), style_body)
            worksheet.write(row, 4, line.get("tipo_operacion", ""), style_body)

            if line.get("fecha_efectiva"):
                worksheet.write_datetime(
                    row,
                    5,
                    fields.Datetime.to_datetime(line["fecha_efectiva"]),
                    style_date,
                )
            else:
                worksheet.write(row, 5, "", style_body)

            worksheet.write(row, 6, line.get("documento_origen", ""), style_body)
            worksheet.write(row, 7, line.get("ubicacion_origen", ""), style_body)
            worksheet.write(row, 8, line.get("ubicacion_destino", ""), style_body)
            worksheet.write(row, 9, line.get("estado", ""), style_body)
            worksheet.write(row, 10, line.get("categoria_producto", ""), style_body)
            worksheet.write(row, 11, line.get("producto", ""), style_body)
            worksheet.write(row, 12, line.get("realizado", 0), style_number)
            worksheet.write(row, 13, line.get("udm", ""), style_body)

            worksheet.write(row, 14, line.get("referencia_pedido", ""), style_body)

            if line.get("fecha_confirmacion"):
                worksheet.write_datetime(
                    row,
                    15,
                    fields.Datetime.to_datetime(line["fecha_confirmacion"]),
                    style_date,
                )
            else:
                worksheet.write(row, 15, "", style_body)

            worksheet.write(row, 16, line.get("proveedor", ""), style_body)
            worksheet.write(row, 17, line.get("cantidad_total", 0), style_number)
            worksheet.write(row, 18, line.get("precio_unitario", 0.0), style_number)
            worksheet.write(row, 19, line.get("impuestos", ""), style_body)
            worksheet.write(row, 20, line.get("moneda", ""), style_body)

            row += 1

        # Congela las primeras 3 filas (cabeceras) y las primeras 4 columnas (hasta referencia)
        worksheet.freeze_panes(3, 4)

        # Aplica filtro automático a toda la tabla de datos
        if len(form_data) > 0:
            worksheet.autofilter(2, 0, row - 1, len(headers) - 1)
