# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    exchange_rate = fields.Float(
        string='Tipo de cambio',
        digits=0,
        readonly=True,
        help='Tipo de cambio de la factura original que se aplicará a la nota de crédito.'
    )

    def _get_exchange_rate_from_move(self, move):
        if move.to_force_exchange_rate:
            return 1 / move.to_force_exchange_rate
        elif move.exchange_rate and move.exchange_rate != 0.0:
            return move.exchange_rate
        return 0.0

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        active_ids = self.env.context.get('active_ids', [])
        active_model = self.env.context.get('active_model', '')
        
        if active_model == 'account.move' and active_ids:
            moves = self.env['account.move'].browse(active_ids)
            for move in moves:
                if move.currency_id and move.currency_id != move.company_currency_id:
                    exchange_rate = self._get_exchange_rate_from_move(move)
                    if exchange_rate:
                        res['exchange_rate'] = exchange_rate
                        break
        
        return res
    
    def _prepare_default_reversal(self, move):
        values = super()._prepare_default_reversal(move)
        
        if move.currency_id and move.currency_id != move.company_currency_id:
            exchange_rate = self._get_exchange_rate_from_move(move)
            if exchange_rate:
                values['to_force_exchange_rate'] = 1 / exchange_rate
                values['exchange_rate_type'] = 'forced'
                values['exchange_rate'] = exchange_rate
        
        return values
