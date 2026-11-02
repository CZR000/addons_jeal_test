# -*- coding: utf-8 -*-
from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.constrains("analytic_distribution", "account_id", "debit", "credit")
    def _check_analytic_required(self):
        """Permite omitir la política analítica en los asientos de cierre.

        Se delega en `super()` en lugar de reimplementar la validación de
        `account_analytic_required`: así el módulo no se rompe si la OCA
        cambia el mensaje o la lógica de la restricción.

        El bypass sólo actúa con la clave de contexto explícita, que únicamente
        se inyecta cuando el usuario confirma en el asistente de cierre.
        """
        if self.env.context.get("skip_analytic_policy_check"):
            return
        return super()._check_analytic_required()
