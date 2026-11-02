# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAnalyticCheckWizard(models.TransientModel):
    _name = "account.analytic.check.wizard"
    _description = "Confirmación de Falta de Analítica (obsoleto)"

    move_id = fields.Many2one(comodel_name="account.move", readonly=True)
    message = fields.Html(readonly=True)
