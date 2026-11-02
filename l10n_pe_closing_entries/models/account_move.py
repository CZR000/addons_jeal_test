# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    is_closing_entry = fields.Boolean(
        string="Asiento de Cierre",
        copy=False,
        readonly=True,
        index="btree_not_null",
        help="Marcado por el asistente de asientos de cierre. Permite identificar "
             "y no duplicar los asientos ya generados para un periodo.",
    )

    closing_level = fields.Integer(
        string="Nivel de Cierre",
        copy=False,
        readonly=True,
        help="Nivel de la cadena de cierre al que corresponde el asiento. "
             "Los niveles más altos se generan primero.",
    )

    closing_date_from = fields.Date(
        string="Cierre: Desde", copy=False, readonly=True, index="btree_not_null"
    )

    closing_date_to = fields.Date(
        string="Cierre: Hasta", copy=False, readonly=True, index="btree_not_null"
    )

    @api.model
    def _get_closing_entry_domain(self, company, date_from, date_to):
        """Dominio canónico de los asientos de cierre vigentes de un periodo.

        Centralizado aquí para que el asistente, las vistas y los tests usen
        exactamente el mismo criterio (DRY).
        """
        return [
            ("company_id", "=", company.id),
            ("is_closing_entry", "=", True),
            ("closing_date_from", "=", date_from),
            ("closing_date_to", "=", date_to),
            ("state", "!=", "cancel"),
        ]
