from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = "account.journal"

    move_type = fields.Selection(
        selection=[
            ("A", "A: Apertura"),
            ("M", "M: Movimiento"),
            ("C", "C: Cierre"),
        ],
        string="Tipo de movimiento",
        default="M",
    )
