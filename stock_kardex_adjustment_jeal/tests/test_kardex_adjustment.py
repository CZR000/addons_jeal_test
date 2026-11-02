# -*- coding: utf-8 -*-
from datetime import date

from odoo.addons.stock_account.tests.test_anglo_saxon_valuation_reconciliation_common import (
    ValuationReconciliationTestCommon,
)
from odoo.exceptions import UserError
from odoo.tests import tagged


class KardexAdjustmentCommon(ValuationReconciliationTestCommon):

    @classmethod
    def setup_independent_company(cls, **kwargs):
        group = cls.env.ref('restrict_journal_creation.group_allow_create_account_journal', raise_if_not_found=False)
        if group:
            cls.env.user.write({'groups_id': [(4, group.id)]})
        return super().setup_independent_company(**kwargs)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.categ = cls.stock_account_product_categ
        cls.categ.property_cost_method = 'average'
        cls.cogs_account = cls.company_data['default_account_expense']
        cls.journal = cls.company_data['default_journal_misc']
        cls.company.write({
            'kardex_adj_journal_id': cls.journal.id,
            'kardex_adj_cogs_account_id': cls.cogs_account.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Concentrado',
            'default_code': 'CO-TEST',
            'is_storable': True,
            'categ_id': cls.categ.id,
        })
        cls.warehouse = cls.env['stock.warehouse'].sudo().create({
            'name': 'Kardex test warehouse', 'code': 'KDXT', 'company_id': cls.company.id,
        })
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        cls.valuation_account = cls.categ.property_stock_valuation_account_id

    def _move(self, qty, price=0.0, entry_date=None):
        incoming = qty > 0
        move = self.env['stock.move'].create({
            'name': 'kardex test',
            'product_id': self.product.id,
            'location_id': (self.supplier_location if incoming else self.stock_location).id,
            'location_dest_id': (self.stock_location if incoming else self.customer_location).id,
            'product_uom': self.product.uom_id.id,
            'product_uom_qty': abs(qty),
            'price_unit': price,
        })
        move._action_confirm()
        move._action_assign()
        move.quantity = abs(qty)
        move.picked = True
        move._action_done()
        if entry_date:
            self._set_entry_date(move, entry_date)
        return move

    def _set_entry_date(self, move, entry_date):
        account_move = move.stock_valuation_layer_ids.account_move_id
        account_move.button_draft()
        account_move.write({'name': False, 'date': entry_date})
        account_move.action_post()

    def _run(self, **vals):
        return self.env['stock.kardex.adjustment'].create(dict({
            'company_id': self.company.id,
            'date_from': date(2026, 1, 1),
            'date_to': date(2026, 1, 31),
            'filter_product_ids': [(6, 0, self.product.ids)],
        }, **vals))

    def _posted_lines(self):
        return self.env['stock.kardex.adjustment.line'].search([
            ('product_id', '=', self.product.id), ('state', '=', 'posted')])

    def _scenario(self):
        """Recepción 10 @ 100, salida de 5 al costo de entonces (100) y una
        segunda recepción 10 @ 130; la salida tiene fecha contable posterior
        a la segunda recepción, así que en el kardex va al promedio 115."""
        self._move(10, 100, date(2026, 1, 2))
        out = self._move(-5, entry_date=date(2026, 1, 20))
        self._move(10, 130, date(2026, 1, 10))
        return out



@tagged('post_install', '-at_install')
class TestKardexAdjustment(KardexAdjustmentCommon):

    def test_cost_adjustment_registered_once(self):
        out = self._scenario()
        out_layer = out.stock_valuation_layer_ids
        run = self._run()
        run.action_compute()
        self.assertEqual(run.adjust_count, 1)
        self.assertAlmostEqual(run.cost_adjust_total, -75.0)
        self.assertEqual(run.to_create_count, 1)

        run.action_generate()
        line = self._posted_lines()
        self.assertEqual(len(line), 1)
        self.assertEqual(line.adjusted_layer_id, out_layer)
        self.assertAlmostEqual(line.amount, -75.0)
        # Asiento con la fecha del movimiento ajustado; la salida no tiene
        # orden de venta: contra la cuenta del asiento de la salida (R7)
        self.assertEqual(line.move_id.date, date(2026, 1, 20))
        self.assertEqual(line.move_id.state, 'posted')
        debit = line.move_id.line_ids.filtered('debit')
        credit = line.move_id.line_ids.filtered('credit')
        output = self.categ.property_stock_account_output_categ_id
        self.assertEqual(line.counterpart_account_id, output)
        self.assertEqual(debit.account_id, output)
        self.assertEqual(credit.account_id, self.valuation_account)
        self.assertEqual(line.move_id.line_ids.product_id, self.product)
        self.assertTrue(line.move_id.ref.startswith('AJUSTE KARDEX COSTO PROMEDIO'))
        # Capa de revaluación vinculada a su asiento
        layer = line.revaluation_layer_id
        self.assertAlmostEqual(layer.value, -75.0)
        self.assertEqual(layer.quantity, 0)
        self.assertEqual(layer.account_move_id, line.move_id)
        self.assertEqual(layer.stock_valuation_layer_id, out_layer)
        # La capa queda en el movimiento, como un costo en destino
        self.assertEqual(out.stock_valuation_layer_ids, out_layer | layer)
        # Valoración de Odoo = kardex, y costo del producto al promedio final
        self.assertAlmostEqual(self.product.value_svl, 1725.0)
        self.assertAlmostEqual(self.product.standard_price, 115.0)
        summary = run.summary_ids
        self.assertAlmostEqual(summary.closing_value, 1725.0)

        # Reproceso: nada que hacer, nada duplicado
        run2 = self._run()
        run2.action_compute()
        self.assertEqual(run2.unchanged_count, 1)
        self.assertEqual(run2.pending_count, 0)
        self.assertAlmostEqual(run2.summary_ids.closing_value, 1725.0)

    def test_changed_adjustment_is_updated(self):
        self._scenario()
        self._run().action_generate()
        line = self._posted_lines()
        move = line.move_id
        # Llega una recepción con fecha anterior a la salida: el promedio cambia
        self._move(10, 160, date(2026, 1, 15))
        run = self._run()
        run.action_compute()
        self.assertEqual(run.to_update_count, 1)
        run.action_generate()
        line = self._posted_lines()
        self.assertEqual(len(line), 1)
        self.assertEqual(line.move_id, move, 'Se actualiza el mismo asiento')
        # Promedio (1000 + 1300 + 1600) / 30 = 130 -> 500 - 650 = -150
        self.assertAlmostEqual(line.amount, -150.0)
        self.assertAlmostEqual(line.revaluation_layer_id.value, -150.0)
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')), 150.0)
        self.assertEqual(move.state, 'posted')
        self.assertAlmostEqual(self.product.value_svl, 3900.0 - 650.0)

    def test_obsolete_adjustment_is_reversed(self):
        out = self._scenario()
        self._run().action_generate()
        line = self._posted_lines()
        # La salida pasa a una fecha anterior a la segunda recepción: ya no hay ajuste
        self._set_entry_date(out, date(2026, 1, 5))
        run = self._run()
        run.action_compute()
        self.assertEqual(run.to_reverse_count, 1)
        run.action_generate()
        self.assertEqual(line.state, 'reversed')
        self.assertTrue(line.reversal_move_ids)
        self.assertEqual(line.reversal_move_ids.date, date(2026, 1, 20))
        self.assertAlmostEqual(self.product.value_svl, 1800.0)
        self.assertFalse(self._posted_lines())

    def test_locked_period_generates_nothing(self):
        self._scenario()
        run = self._run()
        run.action_compute()
        self.company.fiscalyear_lock_date = date(2026, 1, 31)
        with self.assertRaises(UserError):
            run.action_generate()
        self.assertFalse(self._posted_lines())

    def test_manual_entry_included(self):
        self._move(10, 100, date(2025, 12, 20))
        manual = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal.id,
            'date': date(2026, 1, 10),
            'line_ids': [
                (0, 0, {'account_id': self.valuation_account.id, 'product_id': self.product.id,
                        'debit': 50.0, 'credit': 0.0, 'name': 'manual'}),
                (0, 0, {'account_id': self.cogs_account.id, 'debit': 0.0, 'credit': 50.0,
                        'name': 'manual'}),
            ],
        })
        manual.action_post()
        self._move(-5, entry_date=date(2026, 1, 20))
        run = self._run(manual_journal_ids=[(6, 0, self.journal.ids)])
        run.action_compute()
        summary = run.summary_ids
        self.assertAlmostEqual(summary.opening_value, 1000.0)
        self.assertAlmostEqual(summary.manual_value, 50.0)
        # Salida al promedio con el manual: 5 x 105 = 525 -> ajuste +25 en Salida
        self.assertAlmostEqual(run.cost_adjust_total, -25.0)
        self.assertAlmostEqual(summary.closing_value, 525.0)
        excluded = self._run(manual_journal_ids=[(6, 0, self.journal.ids)],
                             excluded_move_ids=[(6, 0, manual.ids)])
        excluded.action_compute()
        self.assertAlmostEqual(excluded.summary_ids.manual_value, 0.0)

    def test_export_xlsx(self):
        self._scenario()
        run = self._run()
        run.action_compute()
        action = run.action_export_xlsx()
        self.assertTrue(run.xlsx_file)
        self.assertIn('xlsx_file', action['url'])
