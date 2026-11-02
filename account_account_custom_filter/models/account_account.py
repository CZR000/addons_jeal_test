# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountAccount(models.Model):
    _inherit = "account.account"

    has_movements = fields.Boolean(
        string="Tiene movimientos",
        compute="_compute_has_movements",
        search="_search_has_movements",
        help="True si la cuenta tiene al menos un apunte contable "
             "posted en cualquiera de las compañías activas.",
    )

    def _compute_has_movements(self):
        """Valor puntual por si algún cliente lo lee — no está stored.

        El uso principal es vía search (_search_has_movements), pero
        Odoo exige compute cuando hay search, así que devolvemos algo
        coherente.
        """
        if not self:
            return
        self.env.cr.execute(
            """
            SELECT DISTINCT account_id
              FROM account_move_line
             WHERE parent_state = 'posted'
               AND company_id = ANY(%s)
               AND account_id = ANY(%s)
            """,
            (self.env.companies.ids, self.ids),
        )
        con_mov = {r[0] for r in self.env.cr.fetchall()}
        for rec in self:
            rec.has_movements = rec.id in con_mov

    def _search_has_movements(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise ValueError(
                "Operador no soportado para has_movements. "
                "Use = True / = False / != True / != False."
            )
        self.env.cr.execute(
            """
            SELECT DISTINCT account_id
              FROM account_move_line
             WHERE parent_state = 'posted'
               AND company_id = ANY(%s)
            """,
            (self.env.companies.ids,),
        )
        ids = [r[0] for r in self.env.cr.fetchall()]
        positive = (operator == "=" and value) or (operator == "!=" and not value)
        return [("id", "in" if positive else "not in", ids)]
