from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo import _


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    @api.constrains('payment_account_id')
    def _check_payment_account_type(self):
        """
        Permite cuentas por cobrar/pagar solo si el diario tiene
        'allow_receivable_accounts' habilitado.
        """
        receivable_payable_types = ('asset_receivable', 'liability_payable')
        for line in self:
            if not line.payment_account_id:
                continue
            account_type = line.payment_account_id.account_type
            if account_type in receivable_payable_types:
                if not line.journal_id.allow_receivable_accounts:
                    raise ValidationError(_(
                        'La cuenta "%s" es de tipo "%s" (Por cobrar/Por pagar). '
                        'Para usar este tipo de cuenta en los métodos de pago del diario "%s", '
                        'debe habilitar la opción "Habilitar cuentas por cobrar/pagar en pagos" '
                        'en la configuración del diario.'
                    ) % (
                        line.payment_account_id.display_name,
                        line.payment_account_id.account_type,
                        line.journal_id.name,
                    ))
