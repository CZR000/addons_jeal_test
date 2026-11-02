# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    compensation_journal_id = fields.Many2one(
        related='company_id.compensation_journal_id',
        readonly=False,
    )
    compensation_exchange_gain_account_id = fields.Many2one(
        related='company_id.compensation_exchange_gain_account_id',
        readonly=False,
    )
    compensation_exchange_loss_account_id = fields.Many2one(
        related='company_id.compensation_exchange_loss_account_id',
        readonly=False,
    )