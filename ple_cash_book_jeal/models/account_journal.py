from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_pe_payment_means_id = fields.Many2one(
        comodel_name='payment.methods.codes',
        string='Medio de pago (PLE)',
        help='Medio de pago SUNAT (tabla 1) que se propone en los pagos y en las líneas de '
             'extracto de este diario, p.ej. 003 Transferencia de fondos. El método de pago '
             'puede definir otro (p.ej. cheques 007).',
    )

    def _l10n_pe_get_payment_means(self, payment_method_line=None):
        """Medio de pago por defecto: el del método de pago o, si no tiene, el del diario."""
        self.ensure_one()
        return (payment_method_line and payment_method_line.l10n_pe_payment_means_id) or self.l10n_pe_payment_means_id
