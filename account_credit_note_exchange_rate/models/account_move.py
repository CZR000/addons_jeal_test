# -*- coding: utf-8 -*-
from odoo import models, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_exchange_rate_to_force(self):
        """
        Obtiene el tipo de cambio a forzar.
        Si to_force_exchange_rate está definido, lo usa directamente.
        Si no, calcula el inverso del exchange_rate.
        """
        self.ensure_one()
        if self.to_force_exchange_rate:
            return self.to_force_exchange_rate
        elif self.exchange_rate and self.exchange_rate != 0.0:
            # exchange_rate es el TC normal (ej: 3.7)
            # to_force_exchange_rate necesita el inverso (ej: 1/3.7 = 0.27)
            return 1 / self.exchange_rate
        return 0.0

    def _reverse_moves(self, default_values_list=None, cancel=False):
        """
        Sobrescribe el método _reverse_moves para copiar el to_force_exchange_rate
        de la factura original a la nota de crédito.
        """
        if default_values_list is None:
            default_values_list = [{} for _ in self]
        
        if len(default_values_list) < len(self):
            default_values_list.extend([{} for _ in range(len(self) - len(default_values_list))])
        
        for move, default_values in zip(self, default_values_list):
            if move.currency_id and move.currency_id != move.company_currency_id:
                force_rate = move._get_exchange_rate_to_force()
                if force_rate:
                    default_values['to_force_exchange_rate'] = force_rate
                    default_values['exchange_rate_type'] = 'forced'
                    default_values['exchange_rate'] = 1 / force_rate
        
        return super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)

    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribe create para asegurar que si se está creando una nota de crédito
        desde una factura, se copie el tipo de cambio correctamente.
        """
        moves = super().create(vals_list)
        
        for move in moves:
            # Si es una nota de crédito y tiene reversed_entry_id
            if move.reversed_entry_id and not move.to_force_exchange_rate:
                original = move.reversed_entry_id
                # Solo para facturas en moneda extranjera
                if original.currency_id and original.currency_id != original.company_currency_id:
                    exchange_rate = original._get_exchange_rate_to_force()
                    if exchange_rate:
                        move.to_force_exchange_rate = exchange_rate
        
        return moves
