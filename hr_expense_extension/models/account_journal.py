# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    """``allow_receivable_accounts`` habilita el uso de cuentas por
    cobrar / pagar como cuenta del método de pago. Se usa
    típicamente en el diario de anticipos.
    """

    _inherit = 'account.journal'

    allow_receivable_accounts = fields.Boolean(
        string='Permitir cuentas por cobrar/pagar',
        default=False,
        help='Si está marcado, este diario puede usar cuentas por cobrar '
             'o por pagar como cuenta del método de pago (por ejemplo, un '
             'diario de anticipos).',
    )
