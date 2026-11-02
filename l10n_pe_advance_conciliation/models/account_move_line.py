# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    l10n_pe_advance_id = fields.Many2one(
        "l10n_pe.advance",
        string="Anticipo enlazado",
        help="Anticipo que esta linea negativa descuenta. Lo asigna el "
             "wizard 'Aplicar anticipos'.",
        copy=False,
        index=True,
    )
