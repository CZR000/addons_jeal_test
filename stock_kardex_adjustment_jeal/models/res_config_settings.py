# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kardex_adj_journal_id = fields.Many2one(
        related='company_id.kardex_adj_journal_id', readonly=False)
    kardex_adj_cogs_account_id = fields.Many2one(
        related='company_id.kardex_adj_cogs_account_id', readonly=False)
    kardex_adj_return_cost_method = fields.Selection(
        related='company_id.kardex_adj_return_cost_method', readonly=False)
    kardex_adj_fx_threshold = fields.Monetary(
        related='company_id.kardex_adj_fx_threshold', readonly=False)
    kardex_adj_manual_journal_ids = fields.Many2many(
        related='company_id.kardex_adj_manual_journal_ids', readonly=False)
    kardex_adj_excluded_account_ids = fields.Many2many(
        related='company_id.kardex_adj_excluded_account_ids', readonly=False)
    kardex_adj_create_layers = fields.Boolean(
        related='company_id.kardex_adj_create_layers', readonly=False)
