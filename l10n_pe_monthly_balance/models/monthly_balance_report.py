from datetime import date as py_date
import calendar

from odoo import models, _, fields


class MonthlyBalanceCustomHandler(models.AbstractModel):
    """Custom handler para el reporte "Balance Mensualizado".

    Construye 14 grupos de columnas a partir del reporte General Ledger:

        | Saldo Inicial | Ene | Feb | … | Dic | Saldo Final |

    Cada grupo contiene una sola columna `balance` (movimiento neto del
    período = debit - credit), exactamente como el Balance de Comprobación
    nativo pero abriendo los 12 meses.

    Compatibilidad Odoo 18 (cambios respecto a v16):
        * ``_dynamic_lines_generator`` ahora recibe ``warnings=None`` como
          parámetro adicional (cambio v17→v18 en account.report.custom.handler).
          Lo propagamos a la llamada del handler de General Ledger.
        * Los dicts de ``options['date']`` y de ``forced_options['date']``
          se construyen con ``report._get_dates_period(...)`` en lugar de
          armarlos a mano; esto agrega las claves ``string`` y ``period_type``
          que el framework v18 espera para el render de cabeceras y para el
          motor de currency_table.
        * Se elimina el botón ``Save`` con ``'action': 'open_report_export_wizard'``.
          En v16 esa acción venía implementada en el framework base; en v18
          solo la implementan handlers específicos (l10n_lu_reports,
          documents_account, etc.). Dejarla provocaría crash al hacer clic.
        * Se preserva la firma de ``_custom_options_initializer`` con
          ``previous_options=None`` por compatibilidad con llamadas internas
          desde ``super()``; el framework v18 siempre pasa el argumento
          posicionalmente.
    """
    _name = 'l10n_pe.monthly.balance.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Monthly Balance Custom Handler'

    # -------------------------------------------------------------------------
    # Caret options
    # -------------------------------------------------------------------------
    def _caret_options_initializer(self):
        # Mismas opciones del Balance de comprobación nativo:
        # click sobre una cuenta → abrir General Ledger o Journal Items.
        return {
            'monthly_balance': [
                {'name': _("General Ledger"), 'action': 'caret_option_open_general_ledger'},
                {'name': _("Journal Items"), 'action': 'open_journal_items'},
            ],
        }

    # -------------------------------------------------------------------------
    # Options / columnas
    # -------------------------------------------------------------------------
    def _custom_options_initializer(self, report, options, previous_options=None):
        """Crea los 14 column groups (Saldo Inicial + 12 meses + Saldo Final)
        forzando el rango anual completo en el filtro de fecha del reporte.
        """
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        # -----------------------------------------------------------------
        # Variantes de exportación
        # -----------------------------------------------------------------
        # Dos XLSX distintos: detalle (desplegado) y resumen (plegado).
        export_variant = (previous_options or {}).get('l10n_pe_monthly_balance_export_variant')

        # Botones del header. v18 nativo aporta PDF + XLSX; aquí los
        # reemplazamos por dos variantes XLSX (y ocultamos PDF a propósito).
        options['buttons'] = [
            {
                'name': _('XLSX Detalle'),
                'sequence': 20,
                'action': 'export_file',
                'action_param': 'export_to_xlsx_detail',
                'file_export_type': _('XLSX Detalle'),
            },
            {
                'name': _('XLSX Resumen'),
                'sequence': 30,
                'action': 'export_file',
                'action_param': 'export_to_xlsx_summary',
                'file_export_type': _('XLSX Resumen'),
            },
        ]

        # Plegado/desplegado solo aplica durante impresión/exportación.
        if self._context.get('print_mode'):
            options['unfolded_lines'] = []
            options['unfold_all'] = export_variant == 'detail'

        # -----------------------------------------------------------------
        # Determinar año objetivo (del filtro de fecha actual; fallback hoy)
        # -----------------------------------------------------------------
        date_dict = options.get('date') or {}
        date_to_str = date_dict.get('date_to') or date_dict.get('date') or date_dict.get('date_from')
        date_from_str = date_dict.get('date_from') or date_dict.get('date') or date_to_str
        date_to = fields.Date.from_string(date_to_str) if date_to_str else fields.Date.context_today(self)
        date_from = fields.Date.from_string(date_from_str) if date_from_str else date_to
        year = date_to.year or date_from.year

        year_start = py_date(year, 1, 1)
        year_end = py_date(year, 12, 31)

        # Fuerza el rango principal del reporte al año calendario completo.
        # v18: usamos _get_dates_period para que options['date'] tenga las
        # claves `string` y `period_type` que el framework necesita.
        options['date'] = report._get_dates_period(year_start, year_end, 'range')
        options['date']['filter'] = 'custom'

        default_group_vals = {'horizontal_groupby_element': {}, 'forced_options': {}}

        def _build_group(group_name, forced_options):
            """Crea un column group (1 header + las columnas existentes)."""
            header_element = [{'name': group_name, 'forced_options': forced_options}]
            col_headers = [header_element, *options['column_headers'][1:]]
            column_group_vals = report._generate_columns_group_vals_recursively(col_headers, default_group_vals)
            columns, column_groups = report._build_columns_from_column_group_vals(forced_options, column_group_vals)
            return header_element, columns, column_groups

        # 1) Saldo Inicial — reutilizamos exactamente la lógica de GL.
        initial_balance_options = self.env['account.general.ledger.report.handler']._get_options_initial_balance(options)
        initial_forced_options = {
            'date': initial_balance_options['date'],
            'include_current_year_in_unaff_earnings': initial_balance_options['include_current_year_in_unaff_earnings'],
        }
        initial_header, initial_columns, initial_column_groups = _build_group(
            _("Saldo Inicial"), initial_forced_options,
        )

        # 2) Columnas mensuales (movimiento neto estricto por mes).
        month_names = [
            _("Enero"), _("Febrero"), _("Marzo"), _("Abril"), _("Mayo"), _("Junio"),
            _("Julio"), _("Agosto"), _("Septiembre"), _("Octubre"), _("Noviembre"), _("Diciembre"),
        ]

        month_headers = []
        month_columns = []
        month_column_groups = {}

        for month in range(1, 13):
            last_day = calendar.monthrange(year, month)[1]
            month_start = py_date(year, month, 1)
            month_end = py_date(year, month, last_day)

            forced_options = {
                # v18: _get_dates_period devuelve un dict completo
                # (date_from, date_to, string, period_type, mode).
                'date': report._get_dates_period(month_start, month_end, 'range'),
                # Asegura movimiento neto estricto del mes (no acumulativo
                # desde inicio de ejercicio).
                'general_ledger_strict_range': True,
            }

            header, cols, col_groups = _build_group(month_names[month - 1], forced_options)
            month_headers += header
            month_columns += cols
            month_column_groups.update(col_groups)

        # 3) Saldo Final — año completo (misma semántica que el Saldo Final
        #    del Balance de comprobación nativo).
        end_forced_options = {
            'date': report._get_dates_period(year_start, year_end, 'range'),
        }
        end_header, end_columns, end_column_groups = _build_group(
            _("Saldo Final"), end_forced_options,
        )

        # Aplicar los nuevos column groups.
        options['column_headers'][0] = initial_header + month_headers + end_header
        options['columns'] = initial_columns + month_columns + end_columns

        options['column_groups'] = {}
        options['column_groups'].update(initial_column_groups)
        options['column_groups'].update(month_column_groups)
        options['column_groups'].update(end_column_groups)

        # Evita que el handler de GL calcule totales debajo de cada sección.
        options['ignore_totals_below_sections'] = True

        report._init_options_order_column(options, previous_options)

    # -------------------------------------------------------------------------
    # Generación de líneas
    # -------------------------------------------------------------------------
    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Reusa el agregador del General Ledger (UNION SQL eficiente entre
        column groups) y convierte cada línea en una fila estilo Trial Balance
        (no desplegable, sin opción de ver journal items inline).

        v18: este método recibe ahora `warnings=None` (parámetro añadido en
        v17→v18 en account.report.custom.handler). Lo propagamos al handler
        de General Ledger para no perder señales del framework.
        """
        lines = [
            line[1]
            for line in self.env['account.general.ledger.report.handler']._dynamic_lines_generator(
                report, options, all_column_groups_expression_totals, warnings=warnings,
            )
        ]

        # Compórtate como Balance de Comprobación: cada cuenta es una fila
        # plana (sin expand a journal items aquí).
        for line in lines[:-1]:
            line.pop('expand_function', None)
            line.pop('groupby', None)
            line.update({
                'unfoldable': False,
                'unfolded': False,
                'class': 'o_account_searchable_line o_account_coa_column_contrast',
            })

            res_model = report._get_model_info_from_id(line['id'])[0]
            if res_model == 'account.account':
                line['caret_options'] = 'monthly_balance'

        return [(0, line) for line in lines]

    def _custom_line_postprocessor(self, report, options, lines):
        # Si la jerarquía está activa, marca las líneas de account.group con
        # la clase CSS de contraste para que el render diferencie agrupadores.
        if options.get('hierarchy'):
            for line in lines:
                model, dummy = report._get_model_info_from_id(line['id'])
                if model == 'account.group':
                    line_classes = line.get('class', '')
                    line['class'] = line_classes + ' o_account_coa_column_contrast_hierarchy'
        return lines

    # -------------------------------------------------------------------------
    # Exportar (2 variantes de Excel)
    # -------------------------------------------------------------------------
    def export_to_xlsx_detail(self, options):
        """XLSX con todas las líneas desplegadas."""
        report = self.env['account.report'].browse(options['report_id'])
        export_options = dict(options or {})
        export_options.update({
            'l10n_pe_monthly_balance_export_variant': 'detail',
            'unfolded_lines': [],
            'unfold_all': True,
        })
        result = report.export_to_xlsx(export_options)
        # v18 export_to_xlsx devuelve {'file_name', 'file_content', 'file_type'}
        # — sobrescribimos el nombre para distinguir la variante.
        result['file_name'] = f"{report.name.lower().replace(' ', '_')}_detalle.xlsx"
        return result

    def export_to_xlsx_summary(self, options):
        """XLSX en vista resumen (plegado / general)."""
        report = self.env['account.report'].browse(options['report_id'])
        export_options = dict(options or {})
        export_options.update({
            'l10n_pe_monthly_balance_export_variant': 'summary',
            'unfolded_lines': [],
            'unfold_all': False,
        })
        result = report.export_to_xlsx(export_options)
        result['file_name'] = f"{report.name.lower().replace(' ', '_')}_resumen.xlsx"
        return result
