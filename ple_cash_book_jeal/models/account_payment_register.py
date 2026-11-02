from odoo import api, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _get_default_means_payment(self):
        return False

    @api.onchange('journal_id', 'payment_method_line_id')
    def _onchange_l10n_pe_payment_means(self):
        for wizard in self.filtered('journal_id'):
            means = wizard.journal_id._l10n_pe_get_payment_means(wizard.payment_method_line_id)
            if means:
                wizard.means_payment_id = means

    def _l10n_pe_resolve_payment_means(self, vals):
        """Sin medio de pago elegido en el asistente, el pago lo toma de su método o diario."""
        if not vals.get('means_payment_id'):
            vals.pop('means_payment_id', None)
        return vals

    def _create_payment_vals_from_wizard(self, batch_result):
        return self._l10n_pe_resolve_payment_means(super()._create_payment_vals_from_wizard(batch_result))

    def _create_payment_vals_from_batch(self, batch_result):
        return self._l10n_pe_resolve_payment_means(super()._create_payment_vals_from_batch(batch_result))
