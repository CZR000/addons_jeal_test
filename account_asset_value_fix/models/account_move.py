# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    book_initial_value = fields.Monetary(
        string='Valor Contable Inicial',
        compute='_compute_book_initial_value',
        store=False,
        currency_field='company_currency_id',
        help='Valor contable del activo al inicio del período de esta depreciación: '
             'Valor Original - Depreciación Acumulada previa. '
             'La primera fila muestra el Valor Original completo.',
    )

    book_remaining_value = fields.Monetary(
        string='Valor Contable Final',
        compute='_compute_book_remaining_value',
        store=False,
        currency_field='company_currency_id',
        help='Valor contable del activo al cierre del período tras aplicar esta depreciación: '
             'Valor Original - Depreciación Acumulada. '
             'La última fila termina exactamente en el Valor No Depreciable.',
    )

    def _compute_book_initial_value(self):
        for move in self:
            asset = move.asset_id
            if asset:
                move.book_initial_value = (
                    asset.original_value
                    - move.asset_depreciated_value
                    + move.depreciation_value
                )
            else:
                move.book_initial_value = 0.0

    def _compute_book_remaining_value(self):
        for move in self:
            asset = move.asset_id
            if asset:
                move.book_remaining_value = asset.original_value - move.asset_depreciated_value
            else:
                move.book_remaining_value = 0.0