from odoo import models


class StockRequestOrderXlsx(models.AbstractModel):
    _name = "report.stock_request_order_report_xlsx.report_sro_xlsx"
    _description = "Reporte XLSX Pedido de Existencias"
    _inherit = "report.report_xlsx.abstract"

    def generate_xlsx_report(self, workbook, data, objects):
        # ---------------------------------------------------------------------------- #
        #                                    COLORES                                   #
        # ---------------------------------------------------------------------------- #
        bg_odoo = "#684C60"
        bg_white = "#FFFFFF"
        font_white = "#FFFFFF"
        font_black = "#000000"

        # ---------------------------------------------------------------------------- #
        #                                    ESTILOS                                   #
        # ---------------------------------------------------------------------------- #
        base_fmt = {
            "font_name": "Arial Narrow",
            "font_size": 11,
            "border": 1,
            "border_color": "black",
            "valign": "vcenter",
        }

        style_title = workbook.add_format({
            **base_fmt,
            "bold": True,
            "font_color": font_white,
            "bg_color": bg_odoo,
            "align": "center",
            "font_size": 20,
        })

        style_headboard = workbook.add_format({
            **base_fmt,
            "bold": True,
            "font_color": font_white,
            "bg_color": bg_odoo,
            "align": "center",
        })

        style_body = workbook.add_format({
            **base_fmt,
            "font_color": font_black,
            "bg_color": bg_white,
            "align": "left",
        })

        # ---------------------------------------------------------------------------- #
        #                                   HOJA                                       #
        # ---------------------------------------------------------------------------- #
        worksheet = workbook.add_worksheet("PEDIDOS DE EXISTENCIA")
        worksheet.set_column("A:A", 10)
        worksheet.set_column("B:Y", 25)
        worksheet.set_row(0, 35)

        # ---------------------------------------------------------------------------- #
        #                                   TÍTULO                                     #
        # ---------------------------------------------------------------------------- #
        worksheet.merge_range(
            "A1:F1",
            "REPORTE PEDIDOS DE EXISTENCIA",
            style_title,
        )

        # ---------------------------------------------------------------------------- #
        #                                   CABECERA                                   #
        # ---------------------------------------------------------------------------- #
        for col, value in enumerate(data["header"]):
            worksheet.write(1, col, value, style_headboard)

        # ---------------------------------------------------------------------------- #
        #                                     DATOS                                    #
        # ---------------------------------------------------------------------------- #
        row = 2
        num_reg = 1
        for line in data["form_data"]:
            worksheet.write(row, 0, num_reg, style_body)
            worksheet.write(row, 1, line["companhia"], style_body)
            worksheet.write(row, 2, line["solicitud_existencia"], style_body)
            worksheet.write(row, 3, line["pedido"], style_body)
            worksheet.write(row, 4, line["producto"], style_body)
            worksheet.write(row, 5, line["categoria"], style_body)
            worksheet.write(row, 6, line["fecha_prevista"], style_body)
            worksheet.write(row, 7, line["politica_entrega"], style_body)
            worksheet.write(row, 8, line["almacen"], style_body)
            worksheet.write(row, 9, line["ubicacion"], style_body)
            worksheet.write(row, 10, line["ruta"], style_body)
            worksheet.write(row, 11, line["area"], style_body)
            worksheet.write(row, 12, line["estado_studio"], style_body)
            worksheet.write(row, 13, line["cant"], style_body)
            worksheet.write(row, 14, line["cant_mano"], style_body)
            worksheet.write(row, 15, line["cant_progreso"], style_body)
            worksheet.write(row, 16, line["cant_finalizada"], style_body)
            worksheet.write(row, 17, line["cant_cancelada"], style_body)
            worksheet.write(row, 18, line["comentario"], style_body)
            worksheet.write(row, 19, line["estado"], style_body)
            worksheet.write(row, 20, line["observaciones"], style_body)
            row += 1
            num_reg += 1