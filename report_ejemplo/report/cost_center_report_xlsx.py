# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools import format_date
import io

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class CostCenterReportXlsx:
    """
    Clase dedicada a generar el reporte Excel
    'Resumen de Gastos por Concepto Distribuido por Centros de Costos'
    A PARTIR DE UNA ESTRUCTURA DE DATOS ANIDADA.
    """

    def __init__(self, wizard, report_data, column_map, column_keys):
        """
        Inicializa el generador de reportes.

        :param wizard: Recordset del asistente (wizard) que llama a este reporte.
                       Se usa para obtener el 'env' y las opciones de filtro.
        :param report_data: Dict anidado: {Plan: {Sub-Plan: {Cuenta: {datos...}}}}
        :param column_map: Dict: {'61': 'Titulo Col 61', ...}
        """
        # --- Atributos de Odoo ---
        # Guardamos el wizard completo para acceder a sus métodos y al 'env'
        self.wizard = wizard
        # Guardamos el 'env' en la raíz de la clase para fácil acceso
        self.env = wizard.env

        # --- Atributos de Datos ---
        self.report_data = report_data
        self.column_map = column_map
        self.column_keys = column_keys

        # --- Atributos de XLSXWriter ---
        self.output = io.BytesIO()
        self.workbook = xlsxwriter.Workbook(self.output, {"in_memory": True})

        hoja = ""
        if self.wizard.report_type == "summary":
            hoja = "ResumGtos x Concep DistrxCCosto"
        elif self.wizard.report_type == "monthly":
            hoja = "Centros de Costos Mov Mensual"
        self.worksheet = self.workbook.add_worksheet(hoja)

        # --- Inicialización Interna ---
        self._define_formats()
        self.grand_totals = {prefix: 0.0 for prefix in self.column_keys}
        self.grand_total_final = 0.0
        # Variable para rastrear la fila actual
        self.current_row = 0

    def _define_formats(self):
        """
        Define los formatos de celda con una jerarquía visual estricta.
        Cada nivel tiene su propio 'peso' visual para que el usuario
        identifique inmediatamente si está viendo un Total General o un detalle.
        """
        # ---------------------------------------------------------------------------- #
        #                               1. Paleta de Colores                           #
        # ---------------------------------------------------------------------------- #
        COLOR_PRIMARY = "#714B67"  # Púrpura Institucional (Cabeceras Principales)
        COLOR_ACCENT = "#002060"  # Azul Marino (Texto Nivel 1)
        COLOR_TEXT_MAIN = "#212529"  # Negro suave (Texto estándar)
        COLOR_TEXT_MUTED = "#6C757D"  # Gris (Texto detalle/cuentas)

        COLOR_BORDER = "#DEE2E6"  # Gris muy claro (Bordes sutiles)

        # Fondos para jerarquía
        BG_LEVEL_1 = "#E9ECEF"  # Gris claro (Fondo Nivel 1)
        BG_LEVEL_2 = "#F8F9FA"  # Blanco humo (Fondo Nivel 2 - opcional)
        BG_WHITE = "#FFFFFF"

        # ------------------------------ 2. Estilos Base ----------------------------- #
        base = {
            "font_name": "Calibri",
            "font_size": 10,
            "font_color": COLOR_TEXT_MAIN,
            "valign": "vcenter",
        }

        # Base numérica
        base_num = {**base, "align": "right", "num_format": "#,##0.00"}

        # Bordes
        border_top = {"top": 1, "top_color": COLOR_BORDER}
        border_bottom = {"bottom": 1, "bottom_color": COLOR_BORDER}
        border_tb = {**border_top, **border_bottom}  # Top & Bottom

        # -------------------------- 3. Títulos del Reporte -------------------------- #
        self.format_title = self.workbook.add_format(
            {
                **base,
                "bold": True,
                "font_size": 14,
                "font_color": COLOR_PRIMARY,
                "align": "center",
            }
        )
        self.format_subtitle = self.workbook.add_format(
            {
                **base,
                "bold": True,
                "font_size": 11,
                "font_color": COLOR_TEXT_MAIN,
                "align": "center",
            }
        )

        # --------------------------- 4. Cabeceras de Tabla -------------------------- #
        self.format_header_col = self.workbook.add_format(
            {
                **base,
                "bold": True,
                "align": "center",
                "bg_color": COLOR_PRIMARY,
                "font_color": BG_WHITE,
                "border": 1,
                "border_color": COLOR_BORDER,
                "text_wrap": True,
            }
        )

        self.format_header_analytic = self.workbook.add_format(
            {
                **base,
                "bold": True,
                "align": "left",
                "indent": 1,
                "bg_color": COLOR_PRIMARY,
                "font_color": BG_WHITE,
                "border": 1,
                "border_color": COLOR_BORDER,
                "text_wrap": True,
            }
        )

        # --------------------------- 5. Jerarquía de Etiquetas (Nombres) ------------ #
        # NIVEL 1: PLAN (El contenedor principal)
        # Visual: Fondo gris, letra azul, negrita, bordes arriba/abajo.
        self.format_level_1 = self.workbook.add_format(
            {
                **base,
                **border_tb,
                "bold": True,
                "font_size": 13,
                "font_color": COLOR_ACCENT,
                "bg_color": BG_LEVEL_1,
                "indent": 0,
            }
        )

        # NIVEL 2: CENTRO DE COSTO
        # Visual: Fondo blanco, letra negra fuerte, ligera indentación.
        self.format_level_2 = self.workbook.add_format(
            {
                **base,
                "bold": True,
                "font_size": 12,
                "font_color": COLOR_TEXT_MAIN,
                "bg_color": BG_WHITE,
                "indent": 2,
            }
        )

        # NIVEL 3: GRUPO CONTABLE
        # Visual: Cursiva (para diferenciar agrupación), indentación media.
        self.format_level_3 = self.workbook.add_format(
            {
                **base,
                "bold": True,
                "italic": True,
                "font_size": 11,
                "font_color": COLOR_TEXT_MAIN,
                "indent": 4,
            }
        )

        # NIVEL 4: CUENTA FINANCIERA (Detalle)
        # Visual: Texto gris (muted), indentación profunda.
        self.format_level_4 = self.workbook.add_format(
            {
                **base,
                "bold": True,
                "font_size": 10,
                "font_color": COLOR_TEXT_MUTED,
                "indent": 8,
            }
        )

        # ---------------------------- 6. Datos Numéricos y Totales ------------------ #
        # DATOS NORMALES (Cuerpo / Nivel 4)
        # Coinciden visualmente con el Nivel 4 (texto gris, pequeño)
        self.format_number_data = self.workbook.add_format(
            {
                **base_num,
                "bold": True,
                "font_size": 10,
                "font_color": COLOR_TEXT_MUTED,
            }
        )

        # TOTAL NIVEL 3 (Grupo)
        # Coincide con Level 3: Cursiva, borde superior sutil
        self.format_total_data_3 = self.workbook.add_format(
            {
                **base_num,
                **border_top,
                "bold": True,
                "italic": True,
                "font_size": 11,
                "font_color": COLOR_TEXT_MAIN,
            }
        )

        # TOTAL NIVEL 2 (Centro de Costo)
        # Coincide con Level 2: Negrita, borde superior más oscuro
        self.format_total_data_2 = self.workbook.add_format(
            {
                **base_num,
                "bold": True,
                "top": 1,
                "top_color": "#ADB5BD",  # Borde un poco más oscuro
                "font_size": 12,
                "bg_color": BG_WHITE,
            }
        )

        # TOTAL NIVEL 1 (Plan) - EL MÁS IMPORTANTE
        # Coincide con Level 1: Fondo gris, azul, negrita. Se ve como una barra de resumen.
        self.format_total_data_1 = self.workbook.add_format(
            {
                **base_num,
                **border_tb,
                "bold": True,
                "font_size": 13,
                "font_color": COLOR_ACCENT,
                "bg_color": BG_LEVEL_1,
            }
        )

        # TOTAL GENERAL FINAL
        self.format_total_data_final = self.workbook.add_format(
            {
                **base_num,
                "bold": True,
                "font_size": 13,
                "font_color": BG_WHITE,
                "bg_color": COLOR_PRIMARY,
                "border": 1,
            }
        )

    def generate_excel_content(self):
        """Genera el contenido binario del archivo Excel."""
        report_type = self.wizard.report_type

        self._write_report_header()

        self._write_table_header()

        if report_type == "summary":
            self._write_summary_body()
        elif report_type == "monthly":
            self._write_monthly_body()

        self._write_table_footer()

        self.workbook.close()
        self.output.seek(0)
        return self.output.read()

    def _write_report_header(self):
        """
        Escribe el encabezado institucional del reporte.

        Incluye:
        1. Nombre de la compañía.
        2. Título del reporte.
        3. Rango de fechas (dinámico).
        4. Moneda de expresión (dinámica).
        """
        # ---------------------------- 1. Datos Dinámicos ---------------------------- #
        wizard = self.wizard
        company = wizard.company_id
        currency = company.currency_id
        report_type = wizard.report_type
        filter_desc = wizard._get_filter_description()

        # Generar texto de moneda dinámico (ej. "* EXPRESADO EN SOLES (PEN) *")
        currency_label = currency.currency_unit_label or currency.name
        currency_text = f"* EXPRESADO EN {currency_label.upper()} ({currency.name}) *"

        # ------------------------- 2. Geometría de la Fusión ------------------------ #
        # Calculamos el ancho total: Columna A (0) + Columnas + Columna Total (1)
        last_col_idx = len(self.column_keys) + 1

        # -------------------------- 3. Escritura de Líneas -------------------------- #
        row = 0

        # Línea 1: Nombre de la Empresa
        self.worksheet.merge_range(
            row, 1, row, last_col_idx, company.name.upper(), self.format_title
        )
        row += 1

        # Línea 2: Título del Reporte
        title = ""
        if report_type == "summary":
            title = _("RESUMEN DE GASTOS POR CONCEPTOS - CENTROS DE COSTOS")
        elif report_type == "monthly":
            title = _("COMPARATIVO CENTRO COSTOS POR CUENTA")

        self.worksheet.merge_range(
            row,
            1,
            row,
            last_col_idx,
            title,
            self.format_subtitle,
        )
        row += 1

        # Línea 3: Descripción del Filtro (Fechas)
        self.worksheet.merge_range(
            row, 1, row, last_col_idx, filter_desc, self.format_subtitle
        )
        row += 1

        # Línea 4: Moneda
        self.worksheet.merge_range(
            row, 1, row, last_col_idx, currency_text, self.format_subtitle
        )

    def _write_table_header(self):
        """
        Escribe las cabeceras de la tabla de datos con mejoras de UX.

        1. Moneda Dinámica: Usa el símbolo real de la compañía (ej. $, S/, Bs.)
           en lugar de "S/" fijo.
        2. Freeze Panes: Congela la cabecera y la primera columna para facilitar
           la navegación en reportes largos.
        3. Constantes: Evita números mágicos para filas y alturas.
        """
        # Fila del título agrupador
        row_super_header = 4
        # Fila de los nombres de columnas
        row_columns = 5

        height_super_header = 30
        height_columns = 45

        # Obtener símbolo de moneda dinámicamente
        company = self.wizard.company_id
        currency_symbol = company.currency_id.symbol

        report_type = self.wizard.report_type

        # ---------------------------------------------------------------------
        # 1. Título Agrupador
        # ---------------------------------------------------------------------
        self.worksheet.set_row(row_super_header, height_super_header)

        if report_type == "summary":
            # Fusionar celdas sobre las columnas de datos
            last_month_col_idx = len(self.column_keys)

            if last_month_col_idx > 0:
                self.worksheet.merge_range(
                    # Row start, Col start
                    row_super_header,
                    1,
                    # Row end, Col end
                    row_super_header,
                    last_month_col_idx,
                    "GASTOS POR CONCEPTOS",
                    self.format_header_col,
                )

        # ---------------------------------------------------------------------
        # 2. Cabeceras de Columnas
        # ---------------------------------------------------------------------
        self.worksheet.set_row(row_columns, height_columns)

        # Columna A: Centro de Costos
        self.worksheet.write(
            row_columns, 0, "CENTRO DE COSTOS", self.format_header_analytic
        )
        self.worksheet.set_column(0, 0, 45)

        # Columnas de Meses / Periodos
        col = 1
        for key in self.column_keys:
            title = self.column_map.get(key, key)
            self.worksheet.write(
                row_columns, col, title.upper(), self.format_header_col
            )
            self.worksheet.set_column(col, col, 18)
            col += 1

        # Columna Final: Total
        # Usamos el símbolo dinámico aquí
        total_title = ""
        if report_type == "summary":
            total_title = f"TOTAL GASTOS ({currency_symbol})"
        elif report_type == "monthly":
            total_title = f"TOTAL"

        self.worksheet.write(row_columns, col, total_title, self.format_header_col)
        self.worksheet.set_column(col, col, 18)

        # ---------------------------------------------------------------------
        # 3. UX: Congelar Paneles
        # ---------------------------------------------------------------------
        # Congela todo lo que esté ENCIMA de la fila 6 y a la IZQUIERDA de la columna B (índice 1).
        self.worksheet.freeze_panes(row_columns + 1, 1)

    def _write_summary_body(self):
        """
        Construye las filas del reporte Excel aplicando jerarquía
        y calculando totales ascendentes:
            1.  Totales Completos: Los totales de cada mes se escriben en la cabecera del Plan y Subplan.
            2.  Jerarquía Dinámica: Ajusta los niveles de agrupación si no existe Subplan.
            3.  Optimización: Variables más cortas y legibles.
        """
        # Fila actual
        row = 6
        # Columna de inicio de datos numéricos
        col_start = 1

        # Formatos
        fmt_txt_1 = self.format_level_1
        fmt_txt_2 = self.format_level_2
        fmt_txt_3 = self.format_level_3

        fmt_total_1 = self.format_total_data_1
        fmt_total_2 = self.format_total_data_2
        fmt_total_3 = self.format_total_data_3
        fmt_num = self.format_number_data

        # =====================================================
        # NIVEL 1: PLANES
        # =====================================================
        for plan_name, subplan_data in self.report_data.items():
            # Escribir Cabecera PLAN
            self.worksheet.write(row, 0, plan_name, fmt_txt_1)
            # Guardamos la fila para inyectar los totales
            row_plan_header = row
            # Inicializar acumuladores del PLAN
            plan_totals = {k: 0.0 for k in self.column_keys}
            plan_grand_total = 0.0

            # El plan es nivel 0
            row += 1

            # =====================================================
            # NIVEL 2: SUBPLANES (Hijo Opcional)
            # =====================================================
            for subplan_name, account_data in subplan_data.items():
                # Guardamos la fila para inyectar los totales
                row_subplan_header = None
                # Inicializar acumuladores del SUBPLAN
                subplan_totals = {k: 0.0 for k in self.column_keys}
                subplan_grand_total = 0.0

                # Determinamos si existe un nivel intermedio
                has_subplan = bool(subplan_name)

                if has_subplan:
                    # Escribir Cabecera SUBPLAN
                    self.worksheet.write(row, 0, f"  {subplan_name}", fmt_txt_2)

                    # Agrupación: Nivel 1 (Hijo de Plan)
                    self.worksheet.set_row(row, options={"level": 1, "hidden": False})

                    row_subplan_header = row
                    row += 1

                # =====================================================
                # NIVEL 3: CUENTAS
                # =====================================================
                for account_name, col_values in account_data.items():
                    # Indentación visual
                    indent = "    " if has_subplan else "  "
                    self.worksheet.write(row, 0, f"{indent}{account_name}", fmt_txt_3)

                    # Si hay SUBPLAN, la cuenta es Nivel 2 (Nieto del Plan).
                    # Si NO hay Subplan, la cuenta es Nivel 1 (Hijo directo del Plan).
                    outline_level = 2 if has_subplan else 1
                    self.worksheet.set_row(
                        row, options={"level": outline_level, "hidden": False}
                    )

                    # Escribir Columnas de Datos
                    row_val_sum = 0.0
                    current_col = col_start

                    for key in self.column_keys:
                        # Escribir celda
                        val = col_values.get(key, 0.0)
                        self.worksheet.write(row, current_col, val, fmt_num)

                        # Acumular: Fila
                        row_val_sum += val
                        # Acumular: Subplan (Local)
                        subplan_totals[key] += val
                        # Acumular: Plan (Global)
                        plan_totals[key] += val
                        # Acumular: Totales del Reporte (Super Global)
                        self.grand_totals[key] += val

                        current_col += 1

                    # Escribir Total Horizontal de la Cuenta
                    self.worksheet.write(row, current_col, row_val_sum, fmt_num)

                    # Acumular totales horizontales
                    subplan_grand_total += row_val_sum
                    plan_grand_total += row_val_sum
                    self.grand_total_final += row_val_sum

                    row += 1  # Siguiente cuenta

                # -----------------------------------------------------
                # CIERRE SUBPLAN: Escribir acumulados en su cabecera
                # -----------------------------------------------------
                if row_subplan_header is not None:
                    # 1. Escribir los totales por columna
                    c_idx = col_start
                    for key in self.column_keys:
                        self.worksheet.write(
                            row_subplan_header,
                            c_idx,
                            subplan_totals[key],
                            fmt_total_2,
                        )
                        c_idx += 1

                    # 2. Escribir el total horizontal del subplan
                    self.worksheet.write(
                        row_subplan_header, c_idx, subplan_grand_total, fmt_total_2
                    )

            # -----------------------------------------------------
            # CIERRE PLAN: Escribir acumulados en su cabecera
            # -----------------------------------------------------
            # 1. Escribir los totales por columna (Meses)
            c_idx = col_start
            for key in self.column_keys:
                self.worksheet.write(
                    row_plan_header, c_idx, plan_totals[key], fmt_total_1
                )
                c_idx += 1

            # 2. Escribir el total horizontal del Plan
            self.worksheet.write(
                row_plan_header, c_idx, plan_grand_total, fmt_total_1
            )

        # Guardar índice final para uso posterior
        self.current_row = row

    def _write_monthly_body(self):
        """
        Renderiza el reporte mensual con jerarquía de 4 niveles.
        Nivel 1: Plan (Color)
          Nivel 2: Centro Costo (Bold)
            Nivel 3: Grupo Contable (Indent)
              Nivel 4: Cuenta Financiera (Detalle)
        """
        report_data = self.report_data.get("data", {})
        column_keys = self.column_keys

        row = 6  # Ajustar según tu header
        col_start = 1

        # Formatos
        fmt_lvl_1 = self.format_level_1
        fmt_lvl_2 = self.format_level_2
        fmt_lvl_3 = self.format_level_3
        fmt_lvl_4 = self.format_level_4

        fmt_total_1 = self.format_total_data_1
        fmt_total_2 = self.format_total_data_2
        fmt_total_3 = self.format_total_data_3
        fmt_num = self.format_number_data

        # =====================================================================
        # NIVEL 1: PLAN
        # =====================================================================
        for plan_name, analytics_data in report_data.items():
            self.worksheet.write(row, 0, plan_name.upper(), fmt_lvl_1)

            row_plan = row
            row += 1
            plan_totals = {k: 0.0 for k in column_keys}
            plan_total_accum = 0.0

            # =================================================================
            # NIVEL 2: CENTRO DE COSTO
            # =================================================================
            for analytic_name, groups_data in analytics_data.items():
                # Indentación visual
                self.worksheet.write(row, 0, analytic_name, fmt_lvl_2)
                self.worksheet.set_row(row, options={"level": 1, "hidden": False})

                row_analytic = row
                row += 1
                analytic_totals = {k: 0.0 for k in column_keys}
                analytic_total_accum = 0.0

                # =============================================================
                # NIVEL 3: GRUPO CONTABLE
                # =============================================================
                for group_name, accounts_data in groups_data.items():
                    self.worksheet.write(row, 0, group_name, fmt_lvl_3)
                    self.worksheet.set_row(row, options={"level": 2, "hidden": False})

                    row_group = row
                    row += 1
                    group_totals = {k: 0.0 for k in column_keys}
                    group_total_accum = 0.0

                    # =========================================================
                    # NIVEL 4: CUENTA FINANCIERA
                    # =========================================================
                    for account_name, month_values in accounts_data.items():
                        # Nombre de cuenta con indentación profunda
                        self.worksheet.write(row, 0, account_name, fmt_lvl_4)
                        self.worksheet.set_row(
                            row, options={"level": 3, "hidden": False}
                        )

                        curr_col = col_start
                        row_sum = 0.0

                        # Columnas de Meses
                        for key in column_keys:
                            val = month_values.get(str(key), 0.0)
                            self.worksheet.write(row, curr_col, val, fmt_num)

                            # Acumuladores
                            row_sum += val
                            group_totals[key] += val
                            analytic_totals[key] += val
                            plan_totals[key] += val
                            # Acumular: Totales del Reporte (Super Global)
                            self.grand_totals[key] += val

                            curr_col += 1

                        # Total Horizontal de la Cuenta
                        self.worksheet.write(row, curr_col, row_sum, fmt_num)

                        # Acumular totales horizontales
                        group_total_accum += row_sum
                        analytic_total_accum += row_sum
                        plan_total_accum += row_sum
                        self.grand_total_final += row_sum

                        row += 1

                    # --- FOOTER NIVEL 3 (GRUPO) ---
                    # Escribimos los totales en la fila del Grupo (Header Injection)
                    c = col_start
                    for key in column_keys:
                        self.worksheet.write(
                            row_group, c, group_totals[key], fmt_total_3
                        )
                        c += 1
                    self.worksheet.write(row_group, c, group_total_accum, fmt_total_3)

                # --- FOOTER NIVEL 2 (CENTRO DE COSTO) ---
                c = col_start
                for key in column_keys:
                    self.worksheet.write(
                        row_analytic, c, analytic_totals[key], fmt_total_2
                    )
                    c += 1
                self.worksheet.write(row_analytic, c, analytic_total_accum, fmt_total_2)

            # --- FOOTER NIVEL 1 (PLAN) ---
            c = col_start
            for key in column_keys:
                self.worksheet.write(row_plan, c, plan_totals[key], fmt_total_1)
                c += 1
            self.worksheet.write(row_plan, c, plan_total_accum, fmt_total_1)

        # Guardar índice final para uso posterior
        self.current_row = row

    def _write_table_footer(self):
        """Escribe la fila de totales generales al final del reporte."""
        row = self.current_row
        report_type = self.wizard.report_type

        if report_type == "summary":
            self.worksheet.write(
                row, 0, "TOTAL COSTO DE PRODUCCIÓN", self.format_total_data_final
            )
        elif report_type == "monthly":
            self.worksheet.write(row, 0, "TOTAL GENERAL", self.format_total_data_final)

        col = 1
        for key in self.column_keys:
            self.worksheet.write(
                row, col, self.grand_totals[key], self.format_total_data_final
            )
            col += 1
        self.worksheet.write(
            row, col, self.grand_total_final, self.format_total_data_final
        )
