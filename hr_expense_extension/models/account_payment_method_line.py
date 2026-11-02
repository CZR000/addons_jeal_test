# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import ValidationError


class AccountPaymentMethodLine(models.Model):
    """Bloquea el uso de cuentas por cobrar / pagar como cuenta del
    método de pago si el diario no tiene ``allow_receivable_accounts=True``.
    """

    _inherit = 'account.payment.method.line'

    @api.constrains('payment_account_id', 'journal_id')
    def _check_payment_account_type(self):
        for line in self:
            account = line.payment_account_id
            if not account:
                continue
            if account.account_type not in (
                'asset_receivable', 'liability_payable',
            ):
                continue
            journal = line.journal_id
            if not journal or not journal.allow_receivable_accounts:
                raise ValidationError(_(
                    'La cuenta "%(account)s" es una cuenta por cobrar/pagar. '
                    'Solo puede usarse como cuenta del método de pago si el '
                    'diario tiene marcado "Permitir cuentas por cobrar/pagar" '
                    '(diario: %(journal)s).',
                    account=account.display_name,
                    journal=(
                        journal.display_name if journal else _('(sin diario)')
                    ),
                ))
