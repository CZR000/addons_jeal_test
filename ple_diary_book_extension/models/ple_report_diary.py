# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools.misc import format_date
from datetime import date, datetime
from openpyxl import load_workbook
from openpyxl.styles import Font
import logging
import base64
import io


_logger = logging.getLogger(__name__)


class PleReportDiary(models.Model):
    _inherit = "ple.report.diary"

    simplified_xls_filename = fields.Char(
        string="Nombre Archivo Interno",
        readonly=True,
        copy=False,
        help="Nombre del archivo Excel generado para uso interno.",
    )

    simplified_xls_binary = fields.Binary(
        string="Reporte Excel Interno",
        readonly=True,
        copy=False,
        help="Copia del reporte original con una cabecera añadida para análisis interno.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear el registro, si viene con el reporte original, generamos el interno.
        """
        records = super().create(vals_list)
        for record in records:
            if record.xls_binary_diary:
                record._generate_and_store_simplified_report()
        return records

    def write(self, vals):
        """
        Al actualizar, si el reporte original cambia, regeneramos el interno.
        """
        res = super().write(vals)
        # Verificamos si el campo 'xls_binary_diary' fue modificado.
        if "xls_binary_diary" in vals:
            for record in self:
                record._generate_and_store_simplified_report()
        return res

    def _generate_and_store_simplified_report(self):
        """
        Orquesta la creación del reporte interno. Lee el original, le añade
        la cabecera y guarda el resultado en los campos 'simplified'.
        """
        self.ensure_one()

        # Si el reporte original se elimina, también eliminamos el interno.
        if not self.xls_binary_diary:
            self.write(
                {
                    "simplified_xls_binary": False,
                    "simplified_xls_filename": False,
                }
            )
            return

        try:
            # Formateo de fechas (inicio y fin del periodo)
            # Usamos format_date para obtener el mes en el idioma correcto (Español).
            formatted_date_start = (
                format_date(self.env, self.date_start, date_format="MMMM y").upper()
                if self.date_start
                else ""
            )

            formatted_date_end = (
                format_date(self.env, self.date_end, date_format="MMMM y").upper()
                if self.date_end
                else ""
            )

            # Obtención de datos de la compañía
            company = self.company_id
            company_vat = company.vat or ""
            company_name = company.name or ""
            company_currency_name = (
                company.currency_id.currency_unit_label or ""
            ).upper()

            # Preparamos los datos de cabecera.
            header_data = {
                "date_start_label": formatted_date_start,  # Ej. "ENERO 2024"
                "date_end_label": formatted_date_end,  # Ej. "DICIEMBRE 2024"
                "company_vat": company_vat,  # Ej. "20611680067"
                "company_name": company_name,  # Ej. "CONNECTED RESOURCES S.A.C."
                "currency_name": company_currency_name,  # Ej. "SOLES"
            }

            # Generamos el archivo Excel en memoria.
            original_bytes = base64.b64decode(self.xls_binary_diary)
            output_stream = self._add_header_to_excel_stream(
                io.BytesIO(original_bytes), header_data
            )

            # Generamos el nombre del archivo.
            company_name = self.company_id.name or "SIN_RUC"
            timestamp = datetime.today().strftime("%Y%m%d")
            filename = f"Libro_Diario_Simplificado_{company_name}_{timestamp}.xlsx"

            # Escribimos los valores en los campos correspondientes.
            self.write(
                {
                    "simplified_xls_binary": base64.b64encode(output_stream.read()),
                    "simplified_xls_filename": filename,
                }
            )
        except Exception as e:
            _logger.error(
                "Fallo al generar el reporte interno para '%s' (ID: %d): %s",
                self.display_name,
                self.id,
                e,
            )
            # Escribir un mensaje de error en el chatter del registro.
            self.message_post(
                body=_("No se pudo generar el reporte interno. Error: %s") % e
            )

    def _add_header_to_excel_stream(self, stream: io.BytesIO, data: dict) -> io.BytesIO:
        """
        Toma un stream de bytes de un Excel, le añade una cabecera y devuelve
        un nuevo stream de bytes con el resultado.
        """
        workbook = load_workbook(stream)
        sheet = workbook.active

        # Inserta 6 filas al principio para la cabecera.
        sheet.insert_rows(1, amount=7)

        # Estilos
        title_font = Font(bold=True, size=12)
        label_font = Font(bold=True, size=11)

        # Escribir cabecera
        sheet["A1"] = "Formato 5.2 - Reporte de libro diario simplificado"
        sheet["A1"].font = title_font

        sheet["A2"], sheet["B2"] = "Periodo Inicio:", data["date_start_label"]
        sheet["A2"].font = label_font

        sheet["A3"], sheet["B3"] = "Periodo Fin:", data["date_end_label"]
        sheet["A3"].font = label_font

        sheet["A4"], sheet["B4"] = "RUC:", data["company_vat"]
        sheet["A4"].font = label_font

        sheet["A5"], sheet["B5"] = "Razón Social:", data["company_name"]
        sheet["A5"].font = label_font

        sheet["A6"], sheet["B6"] = "Expresado en:", data["currency_name"]
        sheet["A6"].font = label_font

        # Ajustar ancho de columnas.
        sheet.column_dimensions["A"].width = 25
        sheet.column_dimensions["B"].width = 40

        # Guardar en un nuevo stream de memoria.
        output_stream = io.BytesIO()
        workbook.save(output_stream)
        output_stream.seek(0)
        return output_stream
