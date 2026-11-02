from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    # Tipo de cambio de "Liquidar saldo" de un informe de gastos (llega como
    # default_ desde la acción). Es un campo y no una clave del contexto: los
    # campos calculados almacenados también se recalculan sin el contexto de la
    # acción (p.ej. al final de una llamada RPC).
    l10n_pe_expense_rate_type = fields.Char(string='Tipo de cambio de la rendición')

    @api.depends('currency_id', 'company_currency_id', 'company_id', 'l10n_pe_expense_rate_type')
    def _compute_exchange_rate_type(self):
        super()._compute_exchange_rate_type()
        for wizard in self.filtered(lambda wizard: wizard.l10n_pe_expense_rate_type and wizard.exchange_rate_type):
            wizard.exchange_rate_type = wizard.l10n_pe_expense_rate_type
