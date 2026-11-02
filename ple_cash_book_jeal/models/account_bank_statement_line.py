from odoo import api, models


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    @api.model_create_multi
    def create(self, vals_list):
        # El asiento de la línea de extracto lleva el medio de pago de la operación
        # (cheque 007, depósito 001) o, si no se deduce, el del diario (editable
        # en la línea o en el asiento).
        means_model = self.env['payment.methods.codes']
        for vals in vals_list:
            if not vals.get('payment_method_id') and vals.get('journal_id'):
                means = (means_model._l10n_pe_from_description(vals.get('payment_ref'))
                         or self.env['account.journal'].browse(vals['journal_id']).l10n_pe_payment_means_id)
                if means:
                    vals['payment_method_id'] = means.id
        return super().create(vals_list)
