from io import BytesIO
import re

# Manejo de importación de xlsxwriter con validación de disponibilidad
try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter

from datetime import datetime, date


class AccountMoveReportXlsx:
    """
    Clase para generar reportes de asientos contables en formato XLSX.
    """

    def __init__(self, obj, processed_results):
        """
        Inicializa la clase con el objeto y los resultados procesados.
        """
        self.obj = obj
        self.processed_results = processed_results

    def get_filter_description(self):
        """
        Genera una descripción basada en el tipo de filtro seleccionado.
        """

        def format_date(date_value):
            """
            Convierte una fecha en formato `date` a `dd-mm-yyyy`.
            Si el valor no es válido, retorna una cadena vacía.
            """
            if not date_value:
                return ""
            if isinstance(date_value, (datetime, date)):
                return date_value.strftime("%d-%m-%Y")
            raise ValueError(
                f"El valor proporcionado no es una fecha válida: {date_value}"
            )

        # Obtiene el tipo de filtro y asegura un valor por defecto
        filter_type = self.obj.filter_by or "none"

        # Define descripción inicial
        filter_description = "Sin filtro"

        if filter_type == "period":
            # Obtén las etiquetas de los campos de selección para el mes y año
            month_label = dict(self.obj._fields["month"].selection).get(
                self.obj.month, ""
            )
            year_label = dict(self.obj._fields["year"].selection).get(self.obj.year, "")
            if month_label and year_label:
                filter_description = f"{month_label.upper()} {year_label}"
            else:
                filter_description = "Período no especificado"

        elif filter_type == "range":
            # Convierte y formatea las fechas de inicio y fin
            start_date = format_date(self.obj.date_start)
            end_date = format_date(self.obj.date_end)
            if start_date and end_date:
                filter_description = f"DEL {start_date} AL {end_date}"
            else:
                filter_description = "Rango de fechas no especificado"

        elif filter_type == "date":
            # Convierte y formatea la fecha específica
            formatted_date = format_date(self.obj.filter_date)
            filter_description = formatted_date or "Fecha específica no especificada"

        return filter_description

    @staticmethod
    def _write_headers_report(
        workbook, worksheet, filter_description, company_vat, company_name
    ):
        """
        Define los estilos y escribe las cabeceras del reporte en la hoja de cálculo.
        """
        # ---------------------------------------------------------------------------- #
        #                         TODO - COLORES PERSONALIZADOS                        #
        # ---------------------------------------------------------------------------- #
        COLOR_BG_ODOO = "#684C60"  # Fondo estilo Odoo
        COLOR_BG_WHITE = "#FFFFFF"  # Fondo blanco
        COLOR_FONT_WHITE = "#FFFFFF"  # Texto blanco
        COLOR_FONT_BLACK = "#000000"  # Texto negro

        # ---------------------------------------------------------------------------- #
        #                                TODO - ESTILOS                                #
        # ---------------------------------------------------------------------------- #
        # Estilo para el título principal
        style_title_headboard = workbook.add_format(
            {
                "bold": True,
                "font_color": COLOR_FONT_BLACK,
                "bg_color": COLOR_BG_WHITE,
                "align": "center",
                "valign": "vcenter",
                "font_size": 14,
                "font_name": "Century Gothic",
            }
        )

        # Estilo para los encabezados de datos generales
        style_header = workbook.add_format(
            {
                "align": "left",
                "valign": "vcenter",
                "bold": True,
                "font_name": "Century Gothic",
                "font_size": 12,
                "text_wrap": True,
            }
        )

        # Estilo para las cabeceras de la tabla
        style_headboard = workbook.add_format(
            {
                "bold": True,
                "font_color": COLOR_FONT_WHITE,
                "bg_color": COLOR_BG_ODOO,
                "align": "center",
                "valign": "vcenter",
                "font_size": 12,
                "font_name": "Century Gothic",
                "border": 1,
                "border_color": "black",
                "text_wrap": True,
            }
        )

        # ---------------------------------------------------------------------------- #
        #                          TODO - CABECERA DEL REPORTE                         #
        # ---------------------------------------------------------------------------- #

        # Título del reporte
        worksheet.merge_range(
            "A2:N2",
            "R E G I S T R O      D E      V E N T A S      E      I N G R E S O S",
            style_title_headboard,
        )

        # Datos de la compañía
        worksheet.write(2, 0, "PERIODO", style_header)
        worksheet.merge_range("B3:E3", f": {filter_description}", style_header)

        worksheet.write(3, 0, "RUC", style_header)
        worksheet.merge_range("B4:E4", f": {company_vat}", style_header)

        worksheet.write(4, 0, "RAZÓN SOCIAL", style_header)
        worksheet.merge_range("B5:E5", f": {company_name}", style_header)

        # ---------------------------------------------------------------------------- #
        #                        TODO - ENCABEZADOS DE LA TABLA                        #
        # ---------------------------------------------------------------------------- #
        # Primera columna: ID registro
        worksheet.merge_range("A7:A12", "ID REG", style_headboard)

        # Columna de fechas
        worksheet.merge_range(
            "B7:B12",
            "Fecha de Emisión del Comprobante de Pago o Documento",
            style_headboard,
        )

        # Detalles del comprobante
        worksheet.merge_range(
            "C7:F9", "Comprobante de Pago o Documento", style_headboard
        )
        worksheet.merge_range("C10:C12", "Tipo", style_headboard)
        worksheet.merge_range("D10:D12", "Número de Serie", style_headboard)
        worksheet.merge_range("E10:E12", "Del", style_headboard)
        worksheet.merge_range("F10:F12", "Al", style_headboard)

        # Detalles de compras
        worksheet.merge_range("G7:I9", "Compras", style_headboard)
        worksheet.merge_range("G10:G12", "Soles", style_headboard)
        worksheet.merge_range("H10:H12", "Dólares", style_headboard)
        worksheet.merge_range("I10:I12", "Cambio Compra", style_headboard)

        # Detalles de ventas
        worksheet.merge_range("J7:L9", "Ventas", style_headboard)
        worksheet.merge_range("J10:J12", "Soles", style_headboard)
        worksheet.merge_range("K10:K12", "Dólares", style_headboard)
        worksheet.merge_range("L10:L12", "Cambio Venta", style_headboard)

        # Promoción y utilidad
        worksheet.merge_range("M7:M12", "Cambio Promoción", style_headboard)
        worksheet.merge_range("N7:N12", "UTILIDAD", style_headboard)

    @staticmethod
    def _write_rows_report(workbook, worksheet, processed_results):
        """
        Escribe las filas de datos procesados en la hoja de cálculo e incluye sumatorias.
        """
        # ---------------------------------------------------------------------------- #
        #                                TODO - ESTILOS                                #
        # ---------------------------------------------------------------------------- #
        style_content = workbook.add_format(
            {
                "align": "center",
                "valign": "vcenter",
                "font_size": 12,
                "font_name": "Aptos Narrow",
                "border": 1,
                "border_color": "black",
            }
        )
        style_date = workbook.add_format(
            {
                "align": "center",
                "valign": "vcenter",
                "font_size": 12,
                "font_name": "Aptos Narrow",
                "num_format": "dd/mm/yy",
                "border": 1,
                "border_color": "black",
            }
        )

        style_number_two_decimal = workbook.add_format(
            {
                "num_format": "#,##0.00",
                "align": "right",
                "valign": "vcenter",
                "font_size": 12,
                "font_name": "Aptos Narrow",
                "border": 1,
                "border_color": "black",
            }
        )
        style_number_four_decimal = workbook.add_format(
            {
                "num_format": "#,##0.0000",
                "align": "right",
                "valign": "vcenter",
                "font_size": 12,
                "font_name": "Aptos Narrow",
                "border": 1,
                "border_color": "black",
            }
        )

        style_total_label = workbook.add_format(
            {
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "font_size": 14,
                "font_name": "Arial",
                "border": 1,
                "border_color": "black",
            }
        )
        style_total_number = workbook.add_format(
            {
                "bold": True,
                "num_format": "#,##0.00",
                "align": "right",
                "valign": "vcenter",
                "font_size": 14,
                "font_name": "Arial",
                "border": 1,
                "border_color": "black",
            }
        )

        # ---------------------------------------------------------------------------- #
        #                           TODO - ESCRITURA DE FILAS                          #
        # ---------------------------------------------------------------------------- #
        start_row = 12

        # Variables para almacenar sumatorias
        total_compras_soles = 0
        total_compras_dolares = 0
        total_ventas_soles = 0
        total_ventas_dolares = 0
        total_utilidad_general = 0

        for registro_index, registro in enumerate(processed_results, start=1):
            # Fechas
            fecha_emision = registro.get("fecha_emision", "")
            # Comprobante
            tipo_comprobante = registro.get("tipo_documento", "")
            numero_serie_comprobante = registro.get("serie", "")
            fecha_del = registro.get("correlativo_inicio", "")
            fecha_al = registro.get("correlativo_fin", "")
            # Detalles de compras
            monto_compra_soles = registro.get("compra_soles", 0)
            monto_compra_dolares = registro.get("compra_dolares", 0)
            tasa_cambio_compra = registro.get("cambio_compra", 0)
            # Detalles de ventas
            monto_venta_soles = registro.get("venta_soles", 0)
            monto_venta_dolares = registro.get("venta_dolares", 0)
            tasa_cambio_venta = registro.get("cambio_venta", 0)
            # Promoción y utilidad
            promocion_tasa_cambio = registro.get("diferencia_promocion", 0)
            utilidad_bruta = registro.get("utilidad", 0)

            # Primera columna: ID del registro
            worksheet.write(start_row, 0, registro_index, style_content)
            # Columna de fechas
            worksheet.write(start_row, 1, fecha_emision, style_date)
            # Detalles del comprobante
            worksheet.write(start_row, 2, tipo_comprobante, style_content)
            worksheet.write(start_row, 3, numero_serie_comprobante, style_content)
            worksheet.write(start_row, 4, fecha_del, style_content)
            worksheet.write(start_row, 5, fecha_al, style_content)
            # Detalles de compras
            worksheet.write(start_row, 6, monto_compra_soles, style_number_two_decimal)
            worksheet.write(
                start_row, 7, monto_compra_dolares, style_number_two_decimal
            )
            worksheet.write(start_row, 8, tasa_cambio_compra, style_number_four_decimal)
            # Detalles de ventas
            worksheet.write(start_row, 9, monto_venta_soles, style_number_two_decimal)
            worksheet.write(
                start_row, 10, monto_venta_dolares, style_number_two_decimal
            )
            worksheet.write(start_row, 11, tasa_cambio_venta, style_number_four_decimal)
            # Promoción y utilidad
            worksheet.write(
                start_row, 12, promocion_tasa_cambio, style_number_four_decimal
            )
            worksheet.write(start_row, 13, utilidad_bruta, style_number_two_decimal)

            # Acumular sumas
            total_compras_soles += monto_compra_soles
            total_compras_dolares += monto_compra_dolares
            total_ventas_soles += monto_venta_soles
            total_ventas_dolares += monto_venta_dolares
            total_utilidad_general += utilidad_bruta

            # Incrementar la fila para la siguiente entrada
            start_row += 1

        # ---------------------------------------------------------------------------- #
        #                           TODO - ESCRITURA DE TOTALES                        #
        # ---------------------------------------------------------------------------- #
        worksheet.merge_range(
            f"D{start_row + 1}:F{start_row + 1}", "TOTALES", style_total_label
        )

        # Total de compras
        worksheet.write(start_row, 6, total_compras_soles, style_total_number)
        worksheet.write(start_row, 7, total_compras_dolares, style_total_number)
        worksheet.write(start_row, 8, "", style_total_label)

        # Total de ventas
        worksheet.write(start_row, 9, total_ventas_soles, style_total_number)
        worksheet.write(start_row, 10, total_ventas_dolares, style_total_number)
        worksheet.write(start_row, 11, "", style_total_label)
        worksheet.write(start_row, 12, "", style_total_label)

        # Total de utilidad
        worksheet.write(start_row, 13, total_utilidad_general, style_total_number)

    def generate_excel_content(self):
        """
        Genera el contenido de un archivo Excel en memoria con los datos procesados.

        Este método crea un archivo Excel en memoria, lo configura con los datos necesarios
        y devuelve su contenido en formato binario.
        """
        # Crear un buffer en memoria para almacenar el archivo Excel
        excel_buffer = BytesIO()

        # Iniciar el libro de Excel en memoria
        workbook = xlsxwriter.Workbook(excel_buffer, {"in_memory": True})

        try:
            # Crear la hoja de trabajo
            worksheet = workbook.add_worksheet("Registro de Ventas e Ingresos (RVI)")

            # Configuración de ancho de columnas para todas las columnas (A:N)
            worksheet.set_column("A:N", 18)

            # Configuración de alto de filas para los resultados procesados
            start_row_index = 12  # Fila donde empiezan los datos
            row_height = 15  # Altura fija de cada fila

            for row_index in range(len(self.processed_results)):
                worksheet.set_row(row_index + start_row_index, row_height)

            # Obtener descripción del filtro y datos de la empresa
            filter_description = self.get_filter_description()
            company_vat = self.obj.company_id.vat or "RUC no especificado"
            company_name = self.obj.company_id.name.upper() or "Nombre no especificado"

            # Escribir las cabeceras del reporte
            self._write_headers_report(
                workbook, worksheet, filter_description, company_vat, company_name
            )

            # Escribir las filas con los datos procesados
            self._write_rows_report(workbook, worksheet, self.processed_results)
        finally:
            # Cerrar el libro de trabajo para finalizar su escritura
            workbook.close()

        # Posicionar el buffer al inicio para su lectura
        excel_buffer.seek(0)

        # Retornar el contenido del archivo Excel en formato binario
        return excel_buffer.read()

    def generate_report_filename(self):
        """
        Genera un nombre de archivo seguro para el reporte en función de la compañía, tipo de documento y filtro.

        Retorna:
            str: Nombre del archivo en formato `REPORTE_VENTAS_INGRESOS_{EMPRESA}_{DOCUMENTO}_{FILTRO}.xlsx`
        """

        def _sanitize_filename(value: str) -> str:
            """Limpia el texto eliminando caracteres no permitidos y normalizando espacios."""
            # Permitir solo letras, números, espacios y guiones
            value = re.sub(r"[^\w\s-]", "", value)
            return value

        # Obtener valores con respaldo predeterminado
        type_document_name = _sanitize_filename(
            getattr(self.obj.type_document_id, "name", "SIN_TIPO")
        ).title()
        company_name = _sanitize_filename(
            getattr(self.obj.company_id, "name", "SIN_EMPRESA")
        ).title()
        filter_description = _sanitize_filename(
            self.get_filter_description() or "SIN_FILTRO"
        ).title()

        # Construcción del nombre del archivo con formato limpio
        return f"REPORTE VENTAS INGRESOS - {company_name}, {type_document_name}, {filter_description}.xlsx"
