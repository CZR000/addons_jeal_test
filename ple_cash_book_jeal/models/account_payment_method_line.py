from odoo import fields, models


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    l10n_pe_payment_means_id = fields.Many2one(
        comodel_name='payment.methods.codes',
        string='Medio de pago (PLE)',
        help='Medio de pago SUNAT (tabla 1) de los pagos con este método, p.ej. cheques 007. '
             'Vacío: el del diario.',
    )
