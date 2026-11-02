# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.tools import sql

# Many2one de account.move hacia account.move de otros módulos de jeal sin
# índice: Odoo las busca al revés al crear o escribir cada asiento (para
# recalcular dependencias) y sin índice cada búsqueda recorre la tabla entera.
# Mismo nombre que el índice de Odoo, para no duplicarlo si el módulo dueño
# agrega index=True.
UNINDEXED_MOVE_REFERENCES = ('destination_move_id', 'l10n_pe_detraction_move_id')

KARDEX_ADJUSTMENT_TYPES = [
    ('cost', 'Costo promedio'),
    ('return', 'Devolución o reingreso al costo de origen'),
    ('fx', 'Tipo de cambio'),
    ('fx_61', 'Destino 61 (complementario de TC)'),
    ('price', 'Diferencia de precio'),
    ('price_61', 'Destino 61 (complementario de precio)'),
    ('production', 'Fabricación o desmontaje'),
]


class AccountMove(models.Model):
    _inherit = 'account.move'

    kardex_adjustment = fields.Boolean(
        string='Ajuste por kardex', readonly=True, copy=False, index=True,
        help='Asiento generado por el proceso de ajuste del kardex valorizado.')
    kardex_adjustment_type = fields.Selection(
        selection=KARDEX_ADJUSTMENT_TYPES, string='Tipo de ajuste kardex',
        readonly=True, copy=False)
    kardex_adjustment_run_id = fields.Many2one(
        comodel_name='stock.kardex.adjustment', string='Proceso de kardex',
        readonly=True, copy=False, ondelete='set null', index='btree_not_null')
    kardex_adjusted_layer_id = fields.Many2one(
        comodel_name='stock.valuation.layer', string='Capa ajustada',
        readonly=True, copy=False, ondelete='set null', index='btree_not_null')
    kardex_adjusted_stock_move_id = fields.Many2one(
        comodel_name='stock.move', string='Movimiento ajustado',
        related='kardex_adjusted_layer_id.stock_move_id', store=True)

    def init(self):
        super().init()
        for column in UNINDEXED_MOVE_REFERENCES:
            index = sql.make_index_name(self._table, column)
            if sql.column_exists(self.env.cr, self._table, column) \
                    and not sql.index_exists(self.env.cr, index):
                sql.create_index(self.env.cr, index, self._table, ['"%s"' % column],
                                 where='"%s" IS NOT NULL' % column)

    def action_open_kardex_adjustment_run(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Proceso de kardex'),
            'res_model': 'stock.kardex.adjustment',
            'view_mode': 'form',
            'res_id': self.kardex_adjustment_run_id.id,
        }


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    kardex_adjustment = fields.Boolean(
        related='move_id.kardex_adjustment', string='Ajuste por kardex', store=True)
    kardex_adjustment_type = fields.Selection(
        related='move_id.kardex_adjustment_type', string='Tipo de ajuste kardex', store=True)
