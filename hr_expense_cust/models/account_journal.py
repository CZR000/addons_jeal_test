from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    allow_receivable_accounts = fields.Boolean(
        string='Habilitar cuentas por cobrar/pagar en pagos',
        default=False,
        help=(
            'Al activar esta opción, los métodos de pago de este diario podrán '
            'usar cuentas de tipo "Por cobrar" o "Por pagar" como cuentas '
            'de recibos/pagos pendientes. Solo habilitar en el diario específico '
            'que lo requiera (ej. Entregas a Rendir).'
        ),
    )
