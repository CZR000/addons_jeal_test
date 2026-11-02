from odoo import api, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _get_default_means_payment(self):
        # ple_cash_book proponía siempre 003 (transferencia), aun para cheques: el
        # medio de pago sale del método de pago o del diario (ver create/onchange).
        return False

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        # Con el diario y el método de pago ya resueltos (pueden venir por defecto).
        for payment, vals in zip(payments, vals_list):
            means = not vals.get('means_payment_id') and payment._l10n_pe_get_default_payment_means()
            if means:
                payment.means_payment_id = means
        return payments

    def _l10n_pe_get_default_payment_means(self):
        self.ensure_one()
        return self.journal_id._l10n_pe_get_payment_means(self.payment_method_line_id)

    @api.onchange('journal_id', 'payment_method_line_id')
    def _onchange_l10n_pe_payment_means(self):
        for payment in self.filtered('journal_id'):
            means = payment._l10n_pe_get_default_payment_means()
            if means:
                payment.means_payment_id = means

    def _generate_move_vals(self, write_off_line_vals=None, force_balance=None, line_ids=None):
        vals = super()._generate_move_vals(write_off_line_vals, force_balance, line_ids)
        vals['payment_method_id'] = self.means_payment_id.id
        return vals

    def write(self, vals):
        res = super().write(vals)
        if 'means_payment_id' in vals:
            # El Libro Bancos lee el medio de pago del asiento.
            for payment in self.filtered('move_id'):
                payment.move_id.payment_method_id = payment.means_payment_id
        return res
