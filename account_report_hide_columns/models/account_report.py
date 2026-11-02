# -*- coding: utf-8 -*-
from collections import Counter

from odoo import fields, models
import logging
_logger = logging.getLogger(__name__)

# Los mismos figure_types que account_reports considera "numericos"
# para la logica de is_zero. Los no-numericos (string, none, etc.) nunca
# se ocultan aunque parezcan "vacios".
NUMBER_FIGURE_TYPES = ('float', 'integer', 'monetary', 'percentage')


class AccountReport(models.Model):
    _inherit = 'account.report'

    filter_hide_0_columns = fields.Selection(
        string="Hide columns at 0",
        selection=[
            ('by_default', "Habilitado de forma predeterminada"),
            ('optional', "Opcional"),
            ('never', "Nunca"),
        ],
        compute=lambda x: x._compute_report_option_filter('filter_hide_0_columns', 'never'),
        readonly=False,
        store=True,
        depends=['root_report_id', 'section_main_report_ids'],
    )

    ####################################################
    # OPTIONS: HIDE COLUMNS AT 0
    ####################################################
    def _init_options_hide_0_columns(self, options, previous_options):
        """ Inyecta el flag `hide_0_columns` en options siguiendo el mismo
            patron que `_init_options_hide_0_lines`.
        """
        if self.filter_hide_0_columns != 'never':
            previous_val = previous_options.get('hide_0_columns')
            if previous_val is not None:
                options['hide_0_columns'] = previous_val
            else:
                options['hide_0_columns'] = self.filter_hide_0_columns == 'by_default'
        else:
            options['hide_0_columns'] = False

    def _get_lines(self, options, all_column_groups_expression_totals=None, warnings=None):
        _logger.warning(
            "[hide_0_columns] _get_lines override HIT - hide_0_columns=%s",
            options.get('hide_0_columns'),
        )
        lines = super()._get_lines(
            options,
            all_column_groups_expression_totals=all_column_groups_expression_totals,
            warnings=warnings,
        )
        if options.get('hide_0_columns'):
            self._apply_hide_0_columns(options, lines)
        return lines

    def _apply_hide_0_columns(self, options, lines):
        """ Detecta indices de columna donde TODAS las lineas visibles tienen
            valor 0/None y las elimina de options y de cada linea. Columnas
            no-numericas nunca se ocultan. Muta options y lines in-place.
        """
        _logger.info(
            "[hide_0_columns] llamado - options.hide_0_columns=%s, #columns=%s, #lines=%s",
            options.get('hide_0_columns'),
            len(options.get('columns') or []),
            len(lines) if lines else 0,
        )
        columns = options.get('columns') or []
        n = len(columns)
        if not n or not lines:
            return
    
        # Marca True para columnas que hay que mantener
        keep = [False] * n
        for line in lines:
            line_cols = line.get('columns') or []
            for i in range(min(n, len(line_cols))):
                if keep[i]:
                    continue
                col = line_cols[i]
                figure_type = col.get('figure_type')
                if figure_type not in NUMBER_FIGURE_TYPES:
                    keep[i] = True
                    continue
                if not col.get('is_zero', True):
                    keep[i] = True
            if all(keep):
                break
                
        _logger.info("[hide_0_columns] keep=%s", keep)
        
        # Nada que ocultar
        if all(keep):
            return
        # Salvaguarda: no dejar el reporte sin columnas
        if not any(keep):
            return
    
        kept_indices = [i for i, k in enumerate(keep) if k]
        surviving_group_keys = {columns[i].get('column_group_key') for i in kept_indices}
    
        # Podar options['columns']
        options['columns'] = [columns[i] for i in kept_indices]
    
        # Podar options['column_groups']
        old_column_groups = options.get('column_groups') or {}
        options['column_groups'] = {
            k: v for k, v in old_column_groups.items() if k in surviving_group_keys
        }
    
        # Podar options['column_headers'] con recalculo de colspans
        self._prune_column_headers(options, keep)
    
        # Podar las columnas de cada linea
        for line in lines:
            line_cols = line.get('columns') or []
            line['columns'] = [
                line_cols[i] for i in kept_indices if i < len(line_cols)
            ]
    
    
    def _prune_column_headers(self, options, keep):
        """ Poda options['column_headers'] usando la invariante estructural de
            Odoo 18: en cada nivel de headers, la suma de los colspans de las
            cells cubre exactamente len(options['columns']). Con eso podemos
            mapear cell -> range de column indices via colspans acumulados y
            filtrar sin asumir producto cartesiano.
    
            keep: lista booleana del tamano ORIGINAL de options['columns']
                  (True = la columna sobrevive).
    
            Si algun nivel no cumple la invariante (por ejemplo bandas
            computadas aparte, columnas de comparacion adhoc), ese nivel se
            deja intacto para no romper el reporte; el resto de niveles se
            podan igual.
        """
        column_headers = options.get('column_headers') or []
        if not column_headers:
            return
    
        n = len(keep)
        new_column_headers = []
    
        for level in column_headers:
            total_colspan = sum(cell.get('colspan', 1) for cell in level)
    
            # Nivel que no cubre toda la lista de columnas -> no lo tocamos
            if total_colspan != n:
                new_column_headers.append(level)
                continue
    
            new_level = []
            idx = 0
            for cell in level:
                span = cell.get('colspan', 1)
                end = idx + span
                # Cuantas columnas del range [idx, end) sobreviven
                surviving = sum(1 for j in range(idx, end) if keep[j])
                if surviving > 0:
                    new_cell = dict(cell)
                    new_cell['colspan'] = surviving
                    new_level.append(new_cell)
                idx = end
            new_column_headers.append(new_level)
    
        options['column_headers'] = new_column_headers

    def get_report_information(self, options):
        """ Reajusta la respuesta para el frontend cuando `hide_0_columns` esta
            activo. En el flujo original, `get_report_information` calcula
            `column_headers_render_data` ANTES de llamar `_get_lines`, por lo
            que el header aun contendria las columnas ocultadas. Aca lo
            recomputamos con el `options` ya podado, y podamos tambien los
            totales por grupo de columna a los grupos sobrevivientes.
        """
        info = super().get_report_information(options)

        # Exponer el modo del filtro al frontend (por consistencia con el resto
        # de flags show_*). Cuando este disponible el template Owl heredado,
        # este flag es el que dispara el toggle interactivo.
        if isinstance(info.get('filters'), dict):
            info['filters']['show_hide_0_columns'] = self.filter_hide_0_columns

        if options.get('hide_0_columns') and info.get('lines'):
            # Recomputar los headers con las columnas ya podadas
            info['column_headers_render_data'] = self._get_column_headers_render_data(options)

            # Podar column_groups_totals a los grupos sobrevivientes
            surviving_keys = set((options.get('column_groups') or {}).keys())
            totals = info.get('column_groups_totals') or {}
            if surviving_keys and totals:
                info['column_groups_totals'] = {
                    k: v for k, v in totals.items() if k in surviving_keys
                }

        return info
