# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    custom_opening_journal_id = fields.Many2one(
        comodel_name='account.journal',
        related='company_id.custom_opening_journal_id',
        string='Diario de Apertura',
        readonly=False,
    )

    custom_tb_exclude_prefixes = fields.Char(
        related='company_id.custom_tb_exclude_prefixes',
        string='Prefijos de cuenta a excluir',
        readonly=False,
    )
