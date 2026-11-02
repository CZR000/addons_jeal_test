# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from datetime import date, datetime
from functools import lru_cache
from calendar import monthrange
import base64
import json


# Importamos la NUEVA clase de reporte que crearemos
from ..report.cost_center_report_xlsx import CostCenterReportXlsx



MONTHS = [
    'Enero',
    'Febrero',
    'Marzo',
    'Abril',
    'Mayo',
    'Junio',
    'Julio',
    'Agosto',
    'Septiembre',
    'Octubre',
    'Noviembre',
    'Diciembre',
]


class CostCenterReportWizard(models.TransientModel):
    """
    Asistente interactivo para la generación de reportes analíticos de Centros de Costos.

    Este wizard permite configurar los filtros contables y analíticos necesarios
    para obtener reportes como:
      1. Resumen de gastos por concepto, distribuido por centro de costo.
      2. Detalle mensual de movimientos contables.
    """

    _name = "cost.center.report.wizard"
    _description = "Asistente de Reportes de Centros de Costos"

    # -------------------------------------------------------------------------
    # Métodos auxiliares (defaults y selecciones)
    # -------------------------------------------------------------------------
    @api.model
    def _default_date_from(self):
        """
        Devuelve el primer día del mes actual.
        """
        today = fields.Date.context_today(self)
        return today.replace(day=1)

    @api.model
    def _default_account_groups(self):
        """
        Devuelve los grupos de cuentas de gasto por defecto (códigos 61–68).
        """
        default_codes = [str(code) for code in range(61, 69)]
        return self.env["account.group"].search(
            [
                ("code_prefix_start", "in", default_codes),
                ("company_id", "=", self.env.company.id),
            ]
        )

    @api.model
    @lru_cache(maxsize=1)
    def _get_available_years(self):
        """
        Lista de tuplas (año, año) desde 2020 hasta el año actual.
        """
        current_year = fields.Date.today().year
        return [(str(year), str(year)) for year in range(2020, current_year + 1)]

    @api.model
    @lru_cache(maxsize=1)
    def _get_month_selection(self):
        """
        Lista traducible de meses para el selector.
        """
        return [(str(i), name) for i, name in enumerate(MONTHS, start=1)]

    # -------------------------------------------------------------------------
    # Campos de criterios generales
    # -------------------------------------------------------------------------
    company_id = fields.Many2one(
        comodel_name="res.company",
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
        help='Compañía sobre la cual se generará el reporte.\n\nPor defecto, se selecciona la empresa activa del usuario.',
    )

    report_type = fields.Selection(
        selection=[
            ("summary", 'Resumen de Gastos por Concepto'),
            ("monthly", 'Movimientos Mensuales Detallados'),
        ],
        string='Tipo de Reporte',
        required=True,
        default="summary",
        help='Seleccione el formato del reporte que desea generar:\n• Resumen: Consolidado por concepto y centro de costo.\n• Detallado: Movimientos contables mes a mes.',
    )

    account_group_ids = fields.Many2many(
        comodel_name="account.group",
        string='Grupos de Cuentas',
        domain="""
            [
                ('company_id', 'in', [company_id, False]),
                ('code_prefix_start', '>=', '10'),
                ('code_prefix_start', '<=', '99')
            ]
        """,
        default=_default_account_groups,
        required=True,
        help='Seleccione los grupos contables (por ejemplo, 61 a 68) que se incluirán en el análisis.\n\nEstos grupos determinan las cuentas de gasto o ingreso a considerar en el reporte.',
    )

    analytic_plan_ids = fields.Many2many(
        comodel_name="account.analytic.plan",
        string='Planes Analíticos',
        help='Filtre los resultados por uno o varios planes analíticos.\n\nSi se deja vacío, se incluirán todos los planes disponibles en la compañía.',
    )

    analytic_account_ids = fields.Many2many(
        comodel_name="account.analytic.account",
        string='Centros de Costo',
        domain="[('company_id', 'in', [company_id, False])]",
        help='Permite limitar el reporte a centros de costo específicos.\n\nSi no se selecciona ninguno, se mostrarán todos los centros de costo.',
    )

    account_ids = fields.Many2many(
        comodel_name="account.account",
        string='Cuentas Contables',
        help='Seleccione cuentas contables específicas (por ejemplo, gastos de operación o ingresos).\n\nSi se deja vacío, el reporte incluirá todas las cuentas configuradas.',
    )

    journal_ids = fields.Many2many(
        comodel_name="account.journal",
        string='Diarios Contables',
        domain="[('company_id', 'in', [company_id, False])]",
        help='Permite filtrar los movimientos por uno o más diarios contables.\n\nSi no se selecciona ningún diario, se incluirán todos los de la compañía.',
    )

    # -------------------------------------------------------------------------
    # Campos de filtrado por fecha
    # -------------------------------------------------------------------------
    date_filter_type = fields.Selection(
        selection=[
            ("period_year", 'Año Específico'),
            ("period_month", 'Mes Específico'),
            ("up_to_period", 'Acumulado al Periodo'),
            ("up_to_date", 'Acumulado a la Fecha'),
            ("range", 'Rango Personalizado'),
        ],
        string='Tipo de Filtro de Fecha',
        required=True,
        default="period_year",
        help='Defina el tipo de filtro temporal a aplicar:\n\n• Año Específico: Solo el año fiscal seleccionado.\n• Mes Específico: Solo el mes del año seleccionado.\n• Acumulado al Periodo: Toda la data Hasta fin del mes del año indicado.\n• Acumulado a la Fecha: toda la data Hasta la fecha indicada.\n• Rango Personalizado: Entre fechas específicas elegidas manualmente.',
    )

    year = fields.Selection(
        selection=_get_available_years,
        string='Año',
        default=lambda self: str(fields.Date.today().year),
        help='Seleccione el año fiscal que desea analizar.',
    )

    month = fields.Selection(
        selection=_get_month_selection,
        string='Mes',
        default=lambda self: str(fields.Date.today().month),
        help='Seleccione el mes correspondiente al periodo de análisis.',
    )

    date_from = fields.Date(
        string='Fecha Inicio',
        default=_default_date_from,
        help='Fecha inicial del rango de análisis.\nLos movimientos generados a partir de esta fecha serán incluidos.',
    )

    date_to = fields.Date(
        string='Fecha Fin',
        default=fields.Date.context_today,
        help='Fecha final del rango de análisis.\nSolo los movimientos hasta esta fecha serán considerados.',
    )

    date_up_to = fields.Date(
        string='Fecha',
        default=fields.Date.context_today,
        help='Incluye todos los movimientos contables registrados hasta la fecha seleccionada.',
    )

    # -------------------------------------------------------------------------
    # Campos para salida de reporte
    # -------------------------------------------------------------------------
    xlsx_filename = fields.Char(
        string='Nombre del Archivo Excel',
        help='Nombre del archivo que se generará con los resultados del reporte.\n\nPuede ser personalizado o se asignará automáticamente según los filtros aplicados.',
    )

    xlsx_binary = fields.Binary(
        string='Archivo Excel Generado',
        help='Archivo Excel generado con el reporte analítico solicitado.\n\nPodrá descargarlo una vez completada la generación.',
    )

    # ---------------------------------------------------------------------------- #
    #                           TODO -METODOS CONSTRAINS                           #
    # ---------------------------------------------------------------------------- #
    @api.constrains("date_filter_type", "date_from", "date_to")
    def _check_date_range(self):
        """
        Valida las fechas solo si el tipo de filtro es 'Rango'.
        - Asegura que ambas fechas estén definidas.
        - Asegura que la fecha de inicio no sea posterior a la de fin.
        """
        for wizard in self:
            if wizard.date_filter_type == "range":
                # Si el tipo es 'range', AMBAS fechas son obligatorias.
                if not wizard.date_from or not wizard.date_to:
                    raise ValidationError(
                        _(
                            "Si filtra por 'Rango', debe especificar una 'Fecha Inicio' y una 'Fecha Fin'."
                        )
                    )

                # Si ambas fechas existen, validar el orden.
                if wizard.date_from > wizard.date_to:
                    raise ValidationError(
                        _("La 'Fecha Inicio' no puede ser posterior a la 'Fecha Fin'.")
                    )

    # ---------------------------------------------------------------------------- #
    #                                 TODO - METODO                                #
    # ---------------------------------------------------------------------------- #
    def _get_filtered_dates(self):
        """
        Calcula el rango de fechas (inicio, fin) según el 'date_filter_type'.

        Lógica de retorno:
        - period_year:  [01/01/YYYY, 31/12/YYYY]
        - period_month: [01/MM/YYYY, 31/MM/YYYY]
        - up_to_period: [None, 31/MM/YYYY] (Todo hasta fin de mes)
        - up_to_date:   [None, Fecha Corte] (Todo hasta la fecha)
        - range:        [Fecha Inicio, Fecha Fin]

        Returns:
            tuple: (date_from, date_to). 'date_from' puede ser None.
        """
        self.ensure_one()
        filter_type = self.date_filter_type

        # ---------------------------------------------------------
        # CASO 1: Filtros basados en Año/Mes (Requieren selectores)
        # ---------------------------------------------------------
        if filter_type in ["period_year", "period_month", "up_to_period"]:
            if not self.year:
                raise UserError(_("Debe seleccionar un Año."))

            year = int(self.year)

            # Lógica para Año Completo
            if filter_type == "period_year":
                date_from = date(year, 1, 1)
                date_to = date(year, 12, 31)
                return date_from, date_to

            # Lógica para Meses (period_month, up_to_period)
            if not self.month:
                raise UserError(_("Debe seleccionar un Mes."))

            month = int(self.month)
            last_day_of_month = date(year, month, 1) + relativedelta(day=31)

            if filter_type == "period_month":
                date_from = date(year, month, 1)
                return date_from, last_day_of_month

            if filter_type == "up_to_period":
                # Retorna None en inicio para traer histórico completo
                return None, last_day_of_month

        # ---------------------------------------------------------
        # CASO 2: Acumulado a una Fecha Específica
        # ---------------------------------------------------------
        elif filter_type == "up_to_date":
            if not self.date_up_to:
                raise UserError(_("Debe seleccionar una Fecha de Corte."))

            # Retorna None en inicio para traer histórico completo
            return None, self.date_up_to

        # ---------------------------------------------------------
        # CASO 3: Rango Personalizado
        # ---------------------------------------------------------
        elif filter_type == "range":
            if not self.date_from or not self.date_to:
                raise UserError(_("Debe seleccionar Fecha Inicio y Fecha Fin."))

            if self.date_from > self.date_to:
                raise UserError(_("La Fecha Inicio no puede ser mayor a la Fecha Fin."))

            return self.date_from, self.date_to

        # ---------------------------------------------------------
        # Fallback (Error)
        # ---------------------------------------------------------
        raise UserError(_("Tipo de filtro de fecha no reconocido."))

    def _get_filter_description(self):
        """
        Genera una descripción legible y humana del rango de fechas aplicado.

        Lógica:
        - Si hay fecha inicio: "DEL 01 DE ENERO DE 2024 AL 31 DE ENERO DE 2024"
        - Si no hay fecha inicio (Acumulado): "AL 31 DE ENERO DE 2024"

        :return: (str) Texto formateado en mayúsculas.
        """
        # 1. Obtener las fechas calculadas (usando tu método refactorizado)
        start_date, end_date = self._get_filtered_dates()

        # 2. Definir el formato de fecha deseado (localizable)
        # 'd' = día, 'MMMM' = nombre mes completo, 'y' = año
        # Las comillas simples 'text' protegen palabras literales en babel
        fmt = "d 'de' MMMM 'de' y"

        # 3. Formatear la fecha final
        end_str = format_date(self.env, end_date, date_format=fmt)

        # 4. Construir la frase
        if start_date:
            # Caso: Rango, Periodo o YTD (Tiene inicio y fin)
            start_str = format_date(self.env, start_date, date_format=fmt)
            description = f"DEL {start_str} AL {end_str}"
        else:
            # Caso: Hasta la Fecha (Sin inicio, es histórico)
            description = f"AL {end_str}"

        # 5. Retornar en mayúsculas
        return description.upper()

    def _build_base_domain(self, date_from, date_to):
        """Construye el dominio base para 'account.analytic.line'."""
        self.ensure_one()
        if not self.account_group_ids:
            raise UserError(
                _(
                    "Debe seleccionar al menos un 'Grupo de Cuentas' para generar este reporte."
                )
            )

        domain = [
            ("company_id", "=", self.company_id.id),
            ("date", "<=", date_to),
            ("account_id", "!=", False),
            ("group_id", "in", self.account_group_ids.ids),
        ]

        if date_from:
            domain.append(("date", ">=", date_from))
        if self.analytic_plan_ids:
            # En Odoo 18 account.analytic.line no tiene plan_id: el plan está en la cuenta analítica.
            # child_of incluye los sub-planes del plan seleccionado.
            domain.append(("account_id.plan_id", "child_of", self.analytic_plan_ids.ids))
        if self.analytic_account_ids:
            domain.append(("account_id", "in", self.analytic_account_ids.ids))
        if self.account_ids:
            domain.append(("general_account_id", "in", self.account_ids.ids))
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))

        return domain

    def _generate_summary_report(self, base_domain):
        """
        Lógica para 'ResumGtos x Concep DistrxCCosto'.
        Construye la estructura de datos anidada.
        """
        self.ensure_one()

        # 1. Definir Columnas (Grupos de Cuentas)
        selected_groups = self.account_group_ids.sorted("code_prefix_start")

        COLUMN_MAP = {
            group.code_prefix_start: f"{group.name.upper()} ({group.code_prefix_start})"
            for group in selected_groups
            if group.code_prefix_start
        }

        COLUMN_PREFIXES = list(COLUMN_MAP.keys())

        group_id_to_prefix_map = {
            group.id: group.code_prefix_start
            for group in selected_groups
            if group.code_prefix_start
        }

        empty_row = {prefix: 0.0 for prefix in COLUMN_PREFIXES}

        # 2. Consultar Apuntes Analíticos
        results = self.env["account.analytic.line"].read_group(
            base_domain,
            fields=["amount"],
            groupby=["account_id", "group_id"],  # Agrupar por C.Analítica y G.Cuenta
            lazy=False,
        )

        if not results:
            raise UserError(
                _(
                    "No se encontraron apuntes analíticos para los filtros seleccionados."
                )
            )

        # 3. Pre-procesar en un Pivote simple
        # { analytic_account_id: {'61': 100, '62': 200, ...}, ... }
        pivot_data = defaultdict(lambda: empty_row.copy())
        analytic_ids_with_data = set()

        for res in results:
            analytic_id = res["account_id"][0]
            group_id = res["group_id"][0]
            amount = res.get("amount", 0.0)
            col_key = group_id_to_prefix_map.get(group_id)

            if not col_key:
                continue

            # Restamos el 'amount' porque los gastos son negativos
            pivot_data[analytic_id][col_key] -= amount
            analytic_ids_with_data.add(analytic_id)

        # 4. Consultar las Cuentas Analíticas (Centros de Costo)
        analytic_accounts = self.env["account.analytic.account"].search(
            [("id", "in", list(analytic_ids_with_data))],
            order="plan_id, code, name",  # Orden multi-nivel
        )

        # 5. CONSTRUIR LA ESTRUCTURA DE DATOS ANIDADA
        # { Plan: { Sub-Plan/Grupo: { C.Analítica: { '61': 0, '62': 0, ... } } } }
        report_data = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

        for acc in analytic_accounts:
            # Nivel 1: Plan Analítico
            plan_name = acc.plan_id.name or _("Sin Plan")
            sub_plan_name = ""

            if acc.plan_id and acc.plan_id.parent_id:
                plan_name = acc.plan_id.parent_id.name or _("Sin Plan")
                # Nivel 2: Sub-Plan (Grupo Analítico Padre)
                sub_plan_name = acc.plan_id.name or _("Sin Sub-Plan")
            # Nivel 3: Cuenta Analítica (Centro de Costo)
            account_name = f"{acc.code} {acc.name}" if acc.code else acc.name
            # Nivel 4: Fila de datos (los valores)
            data_row = pivot_data.get(acc.id)
            # Asignar los datos a la estructura anidada
            report_data[plan_name][sub_plan_name][account_name] = data_row

        if not report_data:
            raise UserError(_("No se pudieron procesar los datos para el reporte."))

        # 6. Convertir defaultdicts a dicts estándar para pasar a la clase Excel
        final_report_data = {
            plan: {sub_plan: dict(accounts) for sub_plan, accounts in sub_plans.items()}
            for plan, sub_plans in report_data.items()
        }

        # 7. Generar el Archivo Excel
        filter_desc = self._get_filter_description()
        filename = f"Resumen_Gastos_x_CC_{filter_desc}.xlsx"

        # Pasamos la nueva estructura de datos
        report_xlsx = CostCenterReportXlsx(
            self, final_report_data, COLUMN_MAP, COLUMN_PREFIXES
        )
        binary_data = report_xlsx.generate_excel_content()

        return base64.b64encode(binary_data), filename

    def parse_month_year(self, text):
        """Convierte un texto como 'setiembre 2024' → (9, 2024)."""

        # Diccionario soportando variaciones ortográficas
        month_map = {
            "enero": 1,
            "febrero": 2,
            "marzo": 3,
            "abril": 4,
            "mayo": 5,
            "junio": 6,
            "julio": 7,
            "agosto": 8,
            "septiembre": 9,
            "setiembre": 9,  # variante aceptada
            "octubre": 10,
            "noviembre": 11,
            "diciembre": 12,
        }

        # Normalizamos texto
        text = text.lower().strip()
        # Separar mes y año
        mes, año = text.split()
        # Convertir a número
        month_number = month_map.get(mes)

        if not month_number:
            raise ValueError(f"Mes no reconocido: {mes}")

        return month_number, int(año)

    def _generate_monthly_move_report(self, base_domain):
        """
        Genera la estructura de datos para el reporte 'Movimientos Mensuales'.

        Estructura de Salida:
        {
            'Plan A': {
                'Centro de Costo 1': {
                    'Grupo 63': {
                        '631100 Cuenta X': {'2024-01': 500.0, '2024-02': 600.0 ...}
                    }
                }
            }
        }
        """
        # 1. Generar Columnas Dinámicas (Meses) basándose en el filtro de fecha
        COLUMN_MAP = {i: name.upper() for i, name in enumerate(MONTHS, start=1)}
        COLUMN_KEYS = list(COLUMN_MAP.keys())

        # 2. Agrupación de Datos (Query Optimizado)
        # Agrupamos por: Mes, Centro de Costo y Cuenta Financiera
        # El Plan y el Grupo se derivan de estos datos.
        aggregated_lines = self.env["account.analytic.line"].read_group(
            domain=base_domain,  # Dominio filtrado según selección de usuario
            fields=["amount"],  # `amount` se suma automáticamente por agrupación
            groupby=[
                "date:month",  # Agrupar por mes (YYYY-MM)
                "general_account_id",  # Agrupación contable formal
                "group_id",  # Agrupación por grupo contable
                "account_id",  # Agrupación por cuenta analítica específica
                # El plan analítico se obtiene luego desde account_id.plan_id
                # (account.analytic.line no tiene campo plan_id en Odoo 18)
            ],
            orderby=(
                "date:month DESC, "
                "general_account_id ASC, "
                "group_id ASC, "
                "account_id ASC"
            ),  # Orden jerárquico descendente por fecha → ascendente dentro de cada nivel
            lazy=False,  # Recupera todos los grupos (necesario para reportes completos)
        )

        if not aggregated_lines:
            raise UserError(
                _("No se encontraron movimientos para el periodo seleccionado.")
            )

        # 3. Recolección de IDs para carga masiva (Evitar N+1)
        analytic_account_ids = set()
        financial_account_ids = set()

        for res in aggregated_lines:
            if res.get("account_id"):
                analytic_account_ids.add(res["account_id"][0])
            if res.get("general_account_id"):
                financial_account_ids.add(res["general_account_id"][0])

        # 4. Mapeo en Memoria (Cache)
        # Mapa: ID Cuenta Analítica -> Objeto (para obtener Plan y Nombre)
        analytic_map = {
            a.id: a
            for a in self.env["account.analytic.account"].browse(
                list(analytic_account_ids)
            )
        }
        # Mapa: ID Cuenta Financiera -> Objeto (para obtener Grupo y Nombre)
        financial_map = {
            a.id: a
            for a in self.env["account.account"].browse(list(financial_account_ids))
        }

        # 5. Construcción de la Jerarquía (4 Niveles)
        # Plan -> Centro de Costo -> Grupo Contable -> Cuenta Financiera -> [Meses]
        report_data = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: defaultdict(lambda: {k: 0.0 for k in COLUMN_KEYS})
                )
            )
        )

        for res in aggregated_lines:
            # Extracción de datos
            date_val = res["date:month"]
            month, year = self.parse_month_year(date_val)
            # Ignorar datos fuera del rango de columnas calculado
            if month not in COLUMN_KEYS:
                continue

            amount = res.get("amount", 0.0) * -1  # Invertir signo (Gastos positivos)

            an_acc_id = res["account_id"][0]
            fin_acc_id = res["general_account_id"][0]

            an_acc = analytic_map.get(an_acc_id)
            fin_acc = financial_map.get(fin_acc_id)

            if not an_acc or not fin_acc:
                continue

            # --- Definición de Niveles ---

            # Nivel 1: Plan Analítico
            # (Si el plan tiene padre, usamos el padre como Nivel 1, o ajusta según tu lógica)
            lvl_1_plan = an_acc.plan_id.name or _("Sin Plan")

            # Nivel 2: Centro de Costo (Cuenta Analítica)
            lvl_2_analytic = (
                f"{an_acc.code} - {an_acc.name}" if an_acc.code else an_acc.name
            )

            # Nivel 3: Grupo Contable (De la cuenta financiera)
            # Usamos el grupo de la cuenta (ej. 63) o los primeros 2 dígitos del código
            if fin_acc.group_id:
                lvl_3_group = (
                    f"{fin_acc.group_id.code_prefix_start} {fin_acc.group_id.name}"
                )
            else:
                prefix = fin_acc.code[:2] if fin_acc.code else "00"
                lvl_3_group = f"Grupo {prefix}"

            # Nivel 4: Cuenta Financiera
            lvl_4_account = f"{fin_acc.code} {fin_acc.name}"

            # Asignación del monto a la celda correspondiente
            report_data[lvl_1_plan][lvl_2_analytic][lvl_3_group][lvl_4_account][
                month
            ] += amount

        # 6. Retorno de Datos
        # Empaquetamos todo para enviarlo al XLSX
        final_data = {
            "data": json.loads(json.dumps(report_data)),
        }

        # 7. Generar el Archivo Excel
        filter_desc = self._get_filter_description()
        filename = f"Centros_de_Costos_Mov_Mensual_{filter_desc}.xlsx"

        # Pasamos la nueva estructura de datos
        report_xlsx = CostCenterReportXlsx(self, final_data, COLUMN_MAP, COLUMN_KEYS)
        binary_data = report_xlsx.generate_excel_content()

        return base64.b64encode(binary_data), filename

    def _return_wizard_view(self):
        """
        Retorna la vista del wizard para la generación de reportes de ingresos y compras.
        """
        # Obtener la referencia a la vista del formulario del wizard
        wizard_form = self.env.ref("report_ejemplo.view_cost_center_report_wizard_form")

        return {
            "type": "ir.actions.act_window",
            "name": _("Reportes de Centros de Costos"),
            "view_mode": "form",
            "res_model": self._name,
            "views": [(wizard_form.id, "form")],
            "view_id": wizard_form.id,
            "context": {"report_type": False},
            "res_id": self.id,
            "target": "new",
        }

    def action_generate_report(self):
        """
        Punto de entrada único para la generación de todos los reportes.

        Este método lee el contexto para determinar qué reporte específico
        debe generar y delega la lógica a un método privado.
        """
        self.ensure_one()

        # 1. Limpiar el reporte anterior para la UX
        self.write({"xlsx_filename": False, "xlsx_binary": False})

        # 2. Obtener el tipo de reporte desde el contexto del botón
        report_type = self.report_type

        # 3. Obtener los datos comunes
        date_from, date_to = self._get_filtered_dates()
        base_domain = self._build_base_domain(date_from, date_to)

        try:
            # 4. Delegar al método de generación correcto
            if report_type == "summary":
                binary_data, filename = self._generate_summary_report(base_domain)
            elif report_type == "monthly":
                binary_data, filename = self._generate_monthly_move_report(base_domain)
            else:
                raise UserError(_("Tipo de reporte no reconocido: '%s'") % report_type)

            # 5. Guardar el archivo generado en el wizard
            self.write({"xlsx_filename": filename, "xlsx_binary": binary_data})

            # 6. Devolver la acción para permanecer en el wizard y mostrar el enlace
            return self._return_wizard_view()
        except Exception as e:
            # Manejo de errores durante la generación o guardado
            raise UserError(f"Error al generar el reporte: {e}")
