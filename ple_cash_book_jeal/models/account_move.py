from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Datos del extracto para decidir el medio de pago (lista «Sin medio de pago»).
    l10n_pe_bank_operation = fields.Char(related='statement_line_id.payment_ref', string='Operación bancaria')
    l10n_pe_bank_amount = fields.Monetary(
        related='statement_line_id.amount',
        string='Importe banco',
        currency_field='l10n_pe_bank_currency_id',
    )
    l10n_pe_bank_currency_id = fields.Many2one(related='statement_line_id.currency_id', string='Moneda del extracto bancario')
