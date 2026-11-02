# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    has_destination_account = fields.Boolean(
        string="Usar Cuentas de Destino",
        default=False,
        help="""
            Si se marca, permite especificar una cuenta contable de destino y 
            su contrapartida para esta cuenta analítica. 
            Esto suele usarse para automatizar asientos contables.
        """,
    )

    destination_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de Destino",
        check_company=True,
        company_dependent=True,
        ondelete="restrict",
        domain="[('deprecated', '=', False)]",
        help="Cuenta contable principal a utilizar cuando se mueva un apunte a esta cuenta analítica.",
    )

    destination_account_counterpart_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de Contrapartida",
        check_company=True,
        company_dependent=True,
        ondelete="restrict",
        domain="[('deprecated', '=', False)]",
        help="Cuenta contable de contrapartida para balancear el asiento.",
    )

    @api.onchange("has_destination_account")
    def _onchange_has_destination_account(self):
        """
        Limpia las cuentas de destino si el usuario desmarca la casilla.
        """
        if not self.has_destination_account:
            self.destination_account_id = False
            self.destination_account_counterpart_id = False
