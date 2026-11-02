# -*- coding: utf-8 -*-
import io
import base64
from datetime import datetime, date
from odoo import models, fields, api, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class ExpenseReportExtraField(models.TransientModel):
    _name = 'expense.report.extra.field'
    _description = 'Campo Extra para Reporte de Gastos'

    wizard_id = fields.Many2one('expense.report.wizard', ondelete='cascade')
    field_key = fields.Selection(
        selection='_get_field_selection',
        string='Campo',
        required=True,
    )
    field_label = fields.Char(
        string='Etiqueta en Excel',
        help='Si está vacío se usa la etiqueta del campo.'
    )
    sequence = fields.Integer(string='Secuencia', default=10)

    @api.model
    def _get_field_selection(self):
        fields_data = self.env['account.move.line'].fields_get()
        options = [
            (fname, f"{fdef.get('string') or fname} ({fname})")
            for fname, fdef in fields_data.items()
            if fdef.get('store')
        ]
        return sorted(options, key=lambda x: x[1])

    @api.onchange('field_key')
    def _onchange_field_key(self):
        if self.field_key:
            fdef = self.env['account.move.line'].fields_get([self.field_key])[self.field_key]
            self.field_label = fdef.get('string') or self.field_key


class ExpenseReportWizard(models.TransientModel):
    _name = 'expense.report.wizard'
    _description = 'Wizard para Reporte de Gastos Excel'

    name = fields.Char(
        string='Nombre del archivo',
        default='reporte_gastos.xlsx'
    )
    file_data = fields.Binary(string='Archivo Excel', readonly=True)
    file_name = fields.Char(string='Nombre archivo')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Generado')
    ], default='draft')

    # ================== MODO DE SELECCIÓN ==================
    selection_mode = fields.Selection([
        ('selected', 'Usar registros seleccionados'),
        ('date_range', 'Filtrar por rango de fechas'),
    ], string='Modo de selección', default='selected', required=True,
       help='Selecciona cómo quieres obtener las líneas para el reporte')

    # ================== FILTROS DE FECHA ==================
    date_from = fields.Date(
        string='Fecha Desde',
        default=lambda self: date(date.today().year, 1, 1),
        help='Fecha inicial del filtro (inclusive)'
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        default=fields.Date.context_today,
        help='Fecha final del filtro (inclusive)'
    )

    # ================== CAMPOS ADICIONALES ==================
    extra_field_ids = fields.One2many(
        'expense.report.extra.field',
        'wizard_id',
        string='Campos Adicionales',
        help='Campos adicionales que se agregarán al final del Excel'
    )

    # ================== INFORMACIÓN ==================
    selected_line_ids = fields.Char(
        string='IDs Seleccionados',
        help='IDs de las líneas seleccionadas (almacenado como string)'
    )
    line_count = fields.Integer(
        string='Líneas seleccionadas',
        readonly=True
    )
    filtered_line_count = fields.Integer(
        string='Líneas a exportar',
        compute='_compute_filtered_line_count'
    )

    @api.model
    def default_get(self, fields_list):
        """Obtener valores por defecto incluyendo los IDs seleccionados"""
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['selected_line_ids'] = ','.join(map(str, active_ids))
            res['line_count'] = len(active_ids)
        return res

    def _get_selected_ids(self):
        """Obtiene los IDs seleccionados desde el campo guardado"""
        if self.selected_line_ids:
            return [int(x) for x in self.selected_line_ids.split(',') if x]
        return []

    @api.depends('selection_mode', 'date_from', 'date_to', 'selected_line_ids')
    def _compute_filtered_line_count(self):
        for wizard in self:
            lines = wizard._get_filtered_lines()
            wizard.filtered_line_count = len(lines)

    @api.onchange('selection_mode', 'date_from', 'date_to')
    def _onchange_date_filter(self):
        """Validar fechas al cambiar"""
        if self.selection_mode == 'date_range' and self.date_from and self.date_to:
            if self.date_from > self.date_to:
                return {
                    'warning': {
                        'title': _('Advertencia'),
                        'message': _('La fecha inicial no puede ser mayor que la fecha final.')
                    }
                }

    def _get_filtered_lines(self):
        """Obtiene las líneas según el modo de selección"""
        domain = []

        if self.selection_mode == 'selected':
            # Modo: Usar registros seleccionados manualmente
            active_ids = self._get_selected_ids()
            if not active_ids:
                return self.env['account.move.line']
            domain = [('id', 'in', active_ids)]
        
        elif self.selection_mode == 'date_range':
            # Modo: Filtrar por rango de fechas (busca en TODOS los registros)
            if self.date_from:
                domain.append(('date', '>=', self.date_from))
            if self.date_to:
                domain.append(('date', '<=', self.date_to))

        return self.env['account.move.line'].search(domain)

    def action_generate_report(self):
        """Genera el reporte Excel"""
        self.ensure_one()

        if not xlsxwriter:
            raise UserError(_(
                'La librería xlsxwriter no está instalada. Ejecute: pip install xlsxwriter'
            ))

        # Validar fechas si está en modo de rango de fechas
        if self.selection_mode == 'date_range':
            if not self.date_from or not self.date_to:
                raise UserError(_('Debe especificar ambas fechas para el filtro.'))
            if self.date_from > self.date_to:
                raise UserError(_('La fecha inicial no puede ser mayor que la fecha final.'))

        # Obtener las líneas filtradas
        move_lines = self._get_filtered_lines()

        if not move_lines:
            if self.selection_mode == 'selected':
                raise UserError(_('No se han seleccionado líneas para exportar.'))
            else:
                raise UserError(_(
                    'No hay líneas en el rango de fechas especificado.'
                ))

        # Crear el archivo Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Reporte de Gastos')

        # ================== FORMATOS ==================
        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'fg_color': '#4472C4',
            'font_color': 'white',
            'border': 1,
            'text_wrap': True,
        })

        cell_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
        })

        number_format = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0.00',
        })

        date_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'num_format': 'dd/mm/yyyy',
        })

        # ================== ENCABEZADOS BASE ==================
        headers = [
            'ID',                                    # Columna A
            '3.1 Rubro ESF',                        # Columna B
            '3.20 Rubro EERR',                      # Columna C
            'Compañía',                             # Columna D
            'Cuenta',                               # Columna E
            'Etiqueta',                             # Columna F
            'Fecha',                                # Columna G
            'Referencia',                           # Columna H
            'Saldo',                                # Columna I
            'Socio',                                # Columna J
            'Líneas analíticas/Cuenta Analítica',   # Columna K
            'Líneas analíticas/Importe',            # Columna L
        ]

        # Anchos de columna base
        column_widths = [10, 25, 25, 25, 45, 50, 12, 40, 15, 35, 40, 18]

        # ================== AGREGAR CAMPOS EXTRA ==================
        extra_fields = self.extra_field_ids.sorted('sequence')
        extra_field_info = []
        amll_fields = self.env['account.move.line'].fields_get()
        
        for extra in extra_fields:
            field_name = extra.field_key
            fdef = amll_fields.get(field_name, {})
            field_label = extra.field_label or fdef.get('string') or field_name
            field_type = fdef.get('type')
        
            headers.append(field_label)
            column_widths.append(25)
        
            extra_field_info.append({
                'name': field_name,
                'label': field_label,
                'type': field_type,
                'relation': fdef.get('relation'),
            })

        # Configurar anchos de columna
        for col, width in enumerate(column_widths):
            worksheet.set_column(col, col, width)

        # Escribir encabezados
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Congelar primera fila
        worksheet.freeze_panes(1, 0)

        # ================== DATOS ==================
        row = 1
        base_col_count = 12  # Número de columnas base

        for line in move_lines:
            # Obtener datos de la línea principal
            line_id = line.id
            rubro_esf = line.eeff_ple_id.display_name if line.eeff_ple_id else ''
            rubro_eerr = line.eerr_ple_id.display_name if line.eerr_ple_id else ''
            company = line.company_id.name or ''
            account = line.account_id.display_name if line.account_id else ''
            label = line.name or ''
            line_date = line.date
            reference = line.ref or line.move_id.name or ''
            balance = line.balance or 0.0
            partner = line.partner_id.name if line.partner_id else ''

            # Obtener valores de campos extra
            extra_values = self._get_extra_field_values(line, extra_field_info)

            # Obtener líneas analíticas
            analytic_lines = self._get_analytic_lines(line)

            if analytic_lines:
                first_line = True
                for analytic in analytic_lines:
                    # Escribir columnas base
                    worksheet.write(row, 0, line_id, cell_format)
                    worksheet.write(row, 1, rubro_esf, cell_format)
                    worksheet.write(row, 2, rubro_eerr, cell_format)
                    worksheet.write(row, 3, company, cell_format)
                    worksheet.write(row, 4, account, cell_format)
                    worksheet.write(row, 5, label, cell_format)
                    worksheet.write(row, 6, line_date, date_format)
                    worksheet.write(row, 7, reference, cell_format)

                    # Saldo solo en la primera fila del grupo
                    if first_line:
                        worksheet.write(row, 8, balance, number_format)
                        first_line = False
                    else:
                        worksheet.write(row, 8, '', cell_format)

                    worksheet.write(row, 9, partner, cell_format)
                    worksheet.write(row, 10, analytic.get('account_name', ''), cell_format)
                    worksheet.write(row, 11, analytic.get('amount', 0.0), number_format)

                    # Escribir campos extra
                    self._write_extra_fields(
                        worksheet, row, base_col_count,
                        extra_values, extra_field_info,
                        cell_format, number_format, date_format
                    )

                    row += 1
            else:
                # Si no hay líneas analíticas
                worksheet.write(row, 0, line_id, cell_format)
                worksheet.write(row, 1, rubro_esf, cell_format)
                worksheet.write(row, 2, rubro_eerr, cell_format)
                worksheet.write(row, 3, company, cell_format)
                worksheet.write(row, 4, account, cell_format)
                worksheet.write(row, 5, label, cell_format)
                worksheet.write(row, 6, line_date, date_format)
                worksheet.write(row, 7, reference, cell_format)
                worksheet.write(row, 8, balance, number_format)
                worksheet.write(row, 9, partner, cell_format)
                worksheet.write(row, 10, '', cell_format)
                worksheet.write(row, 11, 0.0, number_format)

                # Escribir campos extra
                self._write_extra_fields(
                    worksheet, row, base_col_count,
                    extra_values, extra_field_info,
                    cell_format, number_format, date_format
                )

                row += 1

        workbook.close()

        # Guardar el archivo
        output.seek(0)
        file_data = base64.b64encode(output.read())

        # Generar nombre de archivo con fechas si se usa filtro por rango
        file_name = self.name
        if self.selection_mode == 'date_range' and self.date_from and self.date_to:
            base_name = self.name.replace('.xlsx', '')
            file_name = f"{base_name}_{self.date_from.strftime('%Y%m%d')}_{self.date_to.strftime('%Y%m%d')}.xlsx"

        self.write({
            'file_data': file_data,
            'file_name': file_name,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'expense.report.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def _get_extra_field_values(self, line, extra_field_info):
        """Obtiene los valores de los campos extra para una línea"""
        values = []
        for field_info in extra_field_info:
            field_name = field_info['name']
            field_type = field_info['type']

            try:
                value = getattr(line, field_name, None)

                # Procesar según el tipo de campo
                if value is None or value is False:
                    if field_type in ('float', 'integer', 'monetary'):
                        processed_value = 0.0
                    else:
                        processed_value = ''
                elif field_type == 'many2one':
                    processed_value = value.display_name if value else ''
                elif field_type == 'many2many':
                    processed_value = ', '.join(value.mapped('display_name')) if value else ''
                elif field_type == 'one2many':
                    processed_value = f'{len(value)} registros' if value else ''
                elif field_type == 'date':
                    processed_value = value
                elif field_type == 'datetime':
                    processed_value = value.strftime('%d/%m/%Y %H:%M:%S') if value else ''
                elif field_type in ('float', 'integer', 'monetary'):
                    processed_value = float(value) if value else 0.0
                elif field_type == 'boolean':
                    processed_value = 'Sí' if value else 'No'
                elif field_type == 'selection':
                    # Obtener el valor de visualización de la selección
                    selection_dict = dict(
                        self.env['account.move.line']._fields[field_name].selection
                    )
                    processed_value = selection_dict.get(value, value) if value else ''
                else:
                    processed_value = str(value) if value else ''

                values.append({
                    'value': processed_value,
                    'type': field_type
                })

            except Exception:
                values.append({
                    'value': '',
                    'type': 'char'
                })

        return values

    def _write_extra_fields(self, worksheet, row, start_col, extra_values,
                            extra_field_info, cell_format, number_format, date_format):
        """Escribe los campos extra en el Excel"""
        for idx, val_info in enumerate(extra_values):
            col = start_col + idx
            value = val_info['value']
            field_type = val_info['type']

            if field_type in ('float', 'integer', 'monetary'):
                worksheet.write(row, col, value, number_format)
            elif field_type == 'date' and value:
                worksheet.write(row, col, value, date_format)
            else:
                worksheet.write(row, col, value, cell_format)

    def _get_analytic_lines(self, move_line):
        """Obtiene las líneas analíticas desde account.analytic.line"""
        analytic_lines = []
        analytic_line_obj = self.env['account.analytic.line']
        lines = analytic_line_obj.search([('move_line_id', '=', move_line.id)])

        for analytic_line in lines:
            analytic_lines.append({
                'account_name': analytic_line.account_id.display_name if analytic_line.account_id else '',
                'amount': analytic_line.amount,
            })

        return analytic_lines

    def action_download(self):
        """Acción para descargar el archivo"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file_data/%s?download=true' % (
                self._name.replace('.', '_'),
                self.id,
                self.file_name
            ),
            'target': 'self',
        }

    def action_reset(self):
        """Resetear el wizard para generar otro reporte"""
        self.ensure_one()
        self.write({
            'state': 'draft',
            'file_data': False,
            'file_name': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'expense.report.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }
