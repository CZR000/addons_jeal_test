# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

LABELS = {
    'cost': 'AJUSTE KARDEX COSTO PROMEDIO',
    'return': 'AJUSTE KARDEX DEVOLUCION AL COSTO DE ORIGEN',
    'fx': 'AJUSTE KARDEX TC FACTURA VS RECEPCION',
    'price': 'AJUSTE KARDEX PRECIO FACTURA VS RECEPCION',
    'production': 'AJUSTE KARDEX FABRICACION',
}
COMPLEMENT_SUFFIX = ' - DESTINO 61'
# Ajustes de factura vs recepción: 20/24 contra la cuenta de costo de ventas
# de ajustes y el complementario de esa cuenta contra la 61.
INVOICE_TYPES = ('fx', 'price')


class StockKardexAdjustmentLine(models.Model):
    """Ajuste registrado del kardex: uno por capa ajustada y tipo de ajuste.

    Guarda la capa ajustada, su capa de revaluación, sus asientos y su importe
    para que un reproceso no duplique nada (5.4): si el importe no cambia no se
    toca, si cambia se actualiza y si ya no aplica se revierte.
    """
    _name = 'stock.kardex.adjustment.line'
    _description = 'Ajuste de kardex registrado'
    _check_company_auto = True
    _order = 'date desc, product_id, id'
    _rec_name = 'name'

    name = fields.Char(string='Glosa', required=True)
    company_id = fields.Many2one(
        comodel_name='res.company', string='Compañía', required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    product_id = fields.Many2one(
        comodel_name='product.product', string='Producto', required=True,
        index=True, check_company=True)
    adjustment_type = fields.Selection(
        selection=[
            ('cost', 'Costo promedio'),
            ('return', 'Devolución o reingreso al costo de origen'),
            ('fx', 'Diferencia de cambio factura vs recepción'),
            ('price', 'Diferencia de precio factura vs recepción'),
            ('production', 'Fabricación o desmontaje'),
        ],
        string='Tipo de ajuste', required=True)
    invoice_id = fields.Many2one(
        comodel_name='account.move', string='Factura', index='btree_not_null',
        ondelete='restrict', help='Factura que origina el ajuste factura vs recepción.')
    counterpart_account_id = fields.Many2one(
        comodel_name='account.account', string='Contrapartida',
        help='Cuenta contra la que se ajusta el inventario: la del asiento del movimiento '
             'ajustado; en ventas, la de costo de ventas de ajustes. Vacía en los ajustes '
             'anteriores a esta regla (costo de ventas de ajustes).')
    date = fields.Date(string='Fecha contable', required=True, index=True)
    amount = fields.Monetary(
        string='Importe', currency_field='currency_id',
        help='Positivo: Entrada en el kardex (aumenta el inventario). '
             'Negativo: Salida.')
    adjusted_layer_id = fields.Many2one(
        comodel_name='stock.valuation.layer', string='Capa ajustada',
        required=True, index=True, ondelete='restrict', check_company=True)
    stock_move_id = fields.Many2one(
        related='adjusted_layer_id.stock_move_id', string='Movimiento', store=True)
    picking_id = fields.Many2one(
        related='stock_move_id.picking_id', string='Guía', store=True)
    adjusted_move_id = fields.Many2one(
        related='adjusted_layer_id.account_move_id', string='Asiento ajustado')
    revaluation_layer_id = fields.Many2one(
        comodel_name='stock.valuation.layer', string='Capa de revaluación',
        readonly=True, ondelete='set null')
    move_id = fields.Many2one(
        comodel_name='account.move', string='Asiento de ajuste', readonly=True,
        ondelete='restrict')
    fx_move_id = fields.Many2one(
        comodel_name='account.move', string='Asiento complementario (61)',
        readonly=True, ondelete='restrict')
    reversal_move_ids = fields.Many2many(
        comodel_name='account.move',
        relation='stock_kardex_adjustment_line_reversal_rel',
        column1='line_id', column2='move_id',
        string='Asientos de reversión', readonly=True)
    state = fields.Selection(
        selection=[('posted', 'Vigente'), ('reversed', 'Revertido')],
        string='Estado', default='posted', required=True, index=True)
    run_id = fields.Many2one(
        comodel_name='stock.kardex.adjustment', string='Último proceso',
        ondelete='set null')

    _sql_constraints = [
        ('unique_layer_type_posted',
         "EXCLUDE (adjusted_layer_id WITH =, adjustment_type WITH =, "
         "(COALESCE(invoice_id, 0)) WITH =, date WITH =) WHERE (state = 'posted')",
         'Ya existe un ajuste vigente de este tipo para la capa, la factura y la fecha.'),
    ]

    # ------------------------------------------------------------------
    # Cuentas y glosas
    # ------------------------------------------------------------------
    @api.model
    def _get_accounts(self, product, company):
        product = product.with_company(company)
        categ = product.categ_id
        valuation = categ.property_stock_valuation_account_id
        variation = categ.property_stock_account_input_categ_id
        cogs = company.kardex_adj_cogs_account_id
        journal = company.kardex_adj_journal_id or categ.property_stock_journal
        missing = []
        if not valuation:
            missing.append(_('cuenta de valoración de la categoría %s', categ.display_name))
        if not variation:
            missing.append(_('cuenta de entrada de existencias (61) de la categoría %s', categ.display_name))
        if not cogs:
            missing.append(_('cuenta de costo de ventas de ajustes de la compañía'))
        if not journal:
            missing.append(_('diario de ajustes de kardex de la compañía (o diario de inventario de la categoría %s)', categ.display_name))
        if missing:
            raise UserError(_('Falta configurar: %s.', ', '.join(missing)))
        return valuation, variation, cogs, journal

    @api.model
    def _label(self, adjustment_type, layer, complement=False, invoice=None):
        base = LABELS.get(adjustment_type, LABELS['cost'])
        if complement:
            base += COMPLEMENT_SUFFIX
        move = layer.stock_move_id
        guide = move.picking_id.name or move.reference or layer.description or ''
        parts = [base, guide, layer.account_move_id.name or '', invoice.name if invoice else '']
        return ' '.join(p for p in parts if p).strip()

    @api.model
    def _move_lines(self, label, product, debit_account, credit_account, amount):
        return [
            Command.create({
                'name': label,
                'account_id': debit_account.id,
                'product_id': product.id,
                'quantity': 0,
                'debit': amount,
                'credit': 0.0,
            }),
            Command.create({
                'name': label,
                'account_id': credit_account.id,
                'product_id': product.id,
                'quantity': 0,
                'debit': 0.0,
                'credit': amount,
            }),
        ]

    def _main_move_lines(self, amount):
        """Inventario 20/24 contra la contrapartida del ajuste (R7); en los de
        factura vs recepción (a), contra la cuenta de costo de ventas de ajustes."""
        self.ensure_one()
        valuation, _variation, cogs, _journal = self._get_accounts(self.product_id, self.company_id)
        counterpart = cogs if self.adjustment_type in INVOICE_TYPES else (self.counterpart_account_id or cogs)
        if amount > 0:
            debit, credit = valuation, counterpart
        else:
            debit, credit = counterpart, valuation
        return self._move_lines(self.name, self.product_id, debit, credit, abs(amount))

    def _fx_move_lines(self, amount):
        """Factura vs recepción (b): costo de ventas de ajustes contra la
        variación 61 de la categoría."""
        self.ensure_one()
        _valuation, variation, cogs, _journal = self._get_accounts(self.product_id, self.company_id)
        label = self._label(self.adjustment_type, self.adjusted_layer_id, complement=True,
                            invoice=self.invoice_id)
        if amount > 0:
            debit, credit = cogs, variation
        else:
            debit, credit = variation, cogs
        return self._move_lines(label, self.product_id, debit, credit, abs(amount))

    def _move_vals(self, ref, line_commands, kardex_type, run=None):
        """Valores del asiento, con la marca de ajuste por kardex (2.2)."""
        self.ensure_one()
        _valuation, _variation, _cogs, journal = self._get_accounts(self.product_id, self.company_id)
        return {
            'move_type': 'entry',
            'journal_id': journal.id,
            'company_id': self.company_id.id,
            'date': self.date,
            'ref': ref,
            'line_ids': line_commands,
            'kardex_adjustment': True,
            'kardex_adjustment_type': kardex_type,
            'kardex_adjustment_run_id': run.id if run else False,
            'kardex_adjusted_layer_id': self.adjusted_layer_id.id,
        }

    @staticmethod
    def _layer_datetime(date):
        return datetime.combine(date, time(12, 0))

    # ------------------------------------------------------------------
    # Registro (en lote: un create y un action_post para todos los asientos)
    # ------------------------------------------------------------------
    @api.model
    def _create_adjustment(self, company, layer, adjustment_type, amount, date, run=None,
                           invoice=None, counterpart=None):
        return self._create_adjustments(company, [{
            'layer': layer, 'type': adjustment_type, 'amount': amount, 'date': date,
            'invoice_id': invoice.id if invoice else False, 'counterpart': counterpart,
        }], run=run)

    @api.model
    def _create_adjustments(self, company, items, run=None):
        """``items``: lista de dict con ``layer`` (capa ajustada), ``type``,
        ``amount``, ``date``, ``invoice_id`` y ``counterpart`` (cuenta)."""
        if not items:
            return self.browse()
        currency = company.currency_id
        invoices = self.env['account.move'].sudo().browse([i['invoice_id'] for i in items if i.get('invoice_id')])
        invoice_by_id = {m.id: m for m in invoices}
        lines = self.sudo().create([{
            'name': self._label(item['type'], item['layer'], invoice=invoice_by_id.get(item.get('invoice_id'))),
            'company_id': company.id,
            'product_id': item['layer'].product_id.id,
            'adjustment_type': item['type'],
            'date': item['date'],
            'amount': currency.round(item['amount']),
            'adjusted_layer_id': item['layer'].id,
            'invoice_id': item.get('invoice_id') or False,
            'counterpart_account_id': item['counterpart'].id if item.get('counterpart') else False,
            'run_id': run.id if run else False,
        } for item in items])
        move_vals, targets = [], []
        for line in lines:
            move_vals.append(line._move_vals(
                line.name, line._main_move_lines(line.amount), line.adjustment_type, run))
            targets.append((line, 'move_id'))
            if line.adjustment_type in INVOICE_TYPES:
                move_vals.append(line._move_vals(
                    line._label(line.adjustment_type, line.adjusted_layer_id, complement=True,
                                invoice=line.invoice_id),
                    line._fx_move_lines(line.amount), '%s_61' % line.adjustment_type, run))
                targets.append((line, 'fx_move_id'))
        moves = self.env['account.move'].sudo().create(move_vals)
        moves.action_post()
        for (line, fname), move in zip(targets, moves):
            line[fname] = move
        if company.kardex_adj_create_layers:
            layers = self.env['stock.valuation.layer'].sudo().create([
                line._layer_vals(line.amount, line.move_id) for line in lines])
            for line, layer in zip(lines, layers):
                line.revaluation_layer_id = layer
        return lines

    def _layer_vals(self, amount, account_move, description=None):
        self.ensure_one()
        vals = {
            'company_id': self.company_id.id,
            'product_id': self.product_id.id,
            'quantity': 0,
            'unit_cost': 0,
            'value': amount,
            'description': description or self.name,
            'stock_move_id': self.adjusted_layer_id.stock_move_id.id,
            'stock_valuation_layer_id': self.adjusted_layer_id.id,
            'account_move_id': account_move.id,
            'kardex_adjustment_line_id': self.id,
        }
        if 'accounting_date' in self.env['stock.valuation.layer']._fields:
            vals['accounting_date'] = self._layer_datetime(self.date)
        return vals

    def _update_amount(self, amount, run=None):
        self._update_amounts({self: amount}, run=run)

    def _update_amounts(self, amounts, run=None):
        """Mismos ajustes con otro importe: los asientos pasan a borrador, se
        reemplazan sus apuntes y se vuelven a publicar todos juntos; la capa
        toma el importe nuevo. ``amounts``: {línea: importe}."""
        if not amounts:
            return
        lines = self.browse([line.id for line in amounts])
        new_amounts = {line.id: line.currency_id.round(amount) for line, amount in amounts.items()}
        moves = (lines.move_id | lines.fx_move_id).sudo()
        moves.button_draft()
        for line in lines:
            amount = new_amounts[line.id]
            line.move_id.sudo().write({'line_ids': [Command.clear()] + line._main_move_lines(amount)})
            if line.fx_move_id:
                line.fx_move_id.sudo().write({'line_ids': [Command.clear()] + line._fx_move_lines(amount)})
        moves.action_post()
        missing = self.env['stock.kardex.adjustment.line']
        for line in lines:
            amount = new_amounts[line.id]
            if line.revaluation_layer_id:
                line.revaluation_layer_id.sudo().write({'value': amount})
            elif line.company_id.kardex_adj_create_layers:
                missing |= line
            line.write({'amount': amount, 'run_id': run.id if run else line.run_id.id})
        if missing:
            layers = self.env['stock.valuation.layer'].sudo().create([
                line._layer_vals(line.amount, line.move_id) for line in missing])
            for line, layer in zip(missing, layers):
                line.revaluation_layer_id = layer

    def _reverse(self, run=None):
        """Los ajustes ya no aplican: se revierten sus asientos con la misma
        fecha (con la misma marca y tipo) y se anula su capa con una capa de
        signo contrario."""
        if not self:
            return
        moves = self.env['account.move'].sudo()
        default_values = []
        for line in self:
            for move in (line.move_id | line.fx_move_id):
                moves |= move
                default_values.append({
                    'date': line.date,
                    'ref': _('Reversión: %s', move.ref or move.name),
                    'kardex_adjustment': True,
                    'kardex_adjustment_type': move.kardex_adjustment_type or (
                        '%s_61' % line.adjustment_type if move == line.fx_move_id else line.adjustment_type),
                    'kardex_adjustment_run_id': run.id if run else move.kardex_adjustment_run_id.id,
                    'kardex_adjusted_layer_id': line.adjusted_layer_id.id,
                })
        reversals = moves._reverse_moves(default_values_list=default_values)
        reversals.action_post()
        reversal_of = {move.reversed_entry_id.id: move for move in reversals}
        layer_vals, layer_lines = [], []
        for line in self:
            main_reversal = reversal_of.get(line.move_id.id)
            if line.revaluation_layer_id:
                layer_vals.append(line._layer_vals(
                    -line.revaluation_layer_id.value, main_reversal,
                    description=_('Reversión: %s', line.name)))
                layer_lines.append(line)
            line_reversals = reversals.filtered(
                lambda m: m.reversed_entry_id in (line.move_id | line.fx_move_id))
            line.write({
                'state': 'reversed',
                'reversal_move_ids': [Command.set(line_reversals.ids)],
                'run_id': run.id if run else line.run_id.id,
            })
        if layer_vals:
            self.env['stock.valuation.layer'].sudo().create(layer_vals)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_open_moves(self):
        moves = self.move_id | self.fx_move_id | self.reversal_move_ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Asientos de ajuste'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }
