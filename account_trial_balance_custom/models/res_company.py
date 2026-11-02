# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    custom_opening_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de Apertura (B.C. Personalizado)',
        domain=[('type', '=', 'general')],
        help='Diario usado para los asientos de apertura. '
             'El Balance de Comprobación Personalizado mostrará '
             'los movimientos de este diario como Saldo Inicial.',
    )

    custom_tb_exclude_prefixes = fields.Char(
        string='Prefijos de cuenta a excluir (B.C. Personalizado)',
        help='Prefijos de código de cuenta separados por comas que se pueden '
             'ocultar en el Balance de Comprobación Personalizado usando el '
             'filtro "Excluir ctas." del reporte. '
             'Ejemplo: 89, 90, 791',
    )
