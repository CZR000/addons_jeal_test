# -*- coding: utf-8 -*-
from odoo import models


class AccountDebitNote(models.TransientModel):
    _inherit = 'account.debit.note'

    def _prepare_default_values(self, move):
        values = super()._prepare_default_values(move)
        if move.currency_id and move.currency_id != move.company_currency_id:
            if move.to_force_exchange_rate:
                values['to_force_exchange_rate'] = move.to_force_exchange_rate
            elif move.exchange_rate and move.exchange_rate != 0.0:
                values['to_force_exchange_rate'] = 1 / move.exchange_rate
        return values
