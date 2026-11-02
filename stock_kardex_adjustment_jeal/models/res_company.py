# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    kardex_adj_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de ajustes de kardex',
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help='Diario de los asientos de ajuste del kardex: el mismo de los '
             'movimientos de inventario (Valoración del inventario, STJ). Si se deja '
             'vacío se usa el diario de inventario de la categoría del producto.',
    )
    kardex_adj_cogs_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta de costo de ventas (ajustes)',
        domain="[('deprecated', '=', False)]",
        help='Contrapartida de los ajustes de costo y de tipo de cambio '
             '(por ejemplo, 6912100).',
    )
    kardex_adj_return_cost_method = fields.Selection(
        selection=[
            ('origin', 'Costo de la salida de origen'),
            ('current', 'Promedio vigente a la fecha de la devolución'),
        ],
        string='Costo de devoluciones de clientes',
        default='origin',
        required=True,
    )
    kardex_adj_fx_threshold = fields.Monetary(
        string='Umbral de ajuste de tipo de cambio',
        currency_field='currency_id',
        default=1.0,
        help='Diferencias de tipo de cambio menores a este importe se '
             'consideran redondeo y no generan ajuste.',
    )
    kardex_adj_manual_journal_ids = fields.Many2many(
        comodel_name='account.journal',
        relation='res_company_kardex_adj_manual_journal_rel',
        column1='company_id',
        column2='journal_id',
        string='Diarios de asientos manuales incluidos',
        help='Los apuntes publicados de estos diarios con producto, en la '
             'cuenta de valoración de su categoría y sin capa de valoración, '
             'se incluyen en el kardex como líneas de solo valor.',
    )
    kardex_adj_excluded_account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='res_company_kardex_adj_excluded_account_rel',
        column1='company_id',
        column2='account_id',
        string='Cuentas excluidas del kardex',
        help='Apuntes manuales en estas cuentas no se incluyen nunca (por '
             'ejemplo, 2810000 mercaderías por recibir).',
    )
    kardex_adj_create_layers = fields.Boolean(
        string='Crear capas de valoración por ajuste',
        default=True,
        help='Crea una capa de revaluación por cada línea de ajuste para que el '
             'informe de valoración de Odoo cuadre con el kardex.',
    )
