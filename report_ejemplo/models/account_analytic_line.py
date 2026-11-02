# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    group_id = fields.Many2one(
        comodel_name="account.group",
        string="Grupo de Cuentas",
        related="general_account_id.group_id",
        store=True,
        readonly=True,
    )
