# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Cuenta Analítica",
        compute="_compute_analytic_account_id",
        store=True,
        index=True,
        groups="analytic.group_analytic_accounting",
    )

    destination_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta Destino",
        compute="_compute_destination_account_id",
        store=True,
        index=True,
    )

    destination_account_ids = fields.Many2many(
        comodel_name="account.account",
        string="Cuentas Destino",
        compute="_compute_destination_account_ids",
        store=False,
    )

    @api.depends("analytic_distribution")
    def _compute_analytic_account_id(self):
        for line in self:
            if not line.analytic_distribution:
                line.analytic_account_id = False
                continue

            # Tomamos la clave con mayor porcentaje de forma más directa y rápida
            best_key = max(
                line.analytic_distribution, key=line.analytic_distribution.get
            )

            try:
                line.analytic_account_id = int(best_key.split(",")[0])
            except (ValueError, TypeError, IndexError):
                line.analytic_account_id = False

    def _get_destination_accounts(self):
        self.ensure_one()
        accounts = self.env["account.account"]
        if not self.account_id.has_destination_account or not self.analytic_distribution:
            return accounts
        analytic_ids = list(dict.fromkeys(
            int(part)
            for key in self.analytic_distribution
            for part in key.split(",")
            if part.isdigit()
        ))
        analytics = self.env["account.analytic.account"].with_company(
            self.company_id
        ).browse(analytic_ids).exists()
        for analytic in analytics.filtered("has_destination_account"):
            accounts |= analytic.destination_account_id
        return accounts

    @api.depends("account_id.has_destination_account", "analytic_distribution", "company_id")
    def _compute_destination_account_id(self):
        for line in self:
            line.destination_account_id = line._get_destination_accounts()[:1]

    @api.depends("account_id.has_destination_account", "analytic_distribution", "company_id")
    def _compute_destination_account_ids(self):
        for line in self:
            line.destination_account_ids = line._get_destination_accounts()
