from datetime import datetime

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestKardexCostAudit(TransactionCase):
    """End-to-end coverage of the Kardex Cost Audit corrections.

    A product is fed valuation layers whose recorded value (raw ``svl.value``)
    deviates from the chronological weighted average cost, reproducing the
    discrepancy reported by the client. The test then checks that the audit
    detects it, that *Recompute Valuation* aligns the recorded value (and the
    audit converges to zero on a re-run), and that *Regularize Entries* posts a
    balanced draft journal entry against the right accounts.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        Account = cls.env['account.account']
        company_ids = [(6, 0, cls.company.ids)]
        cls.acc_valuation = Account.create({
            'name': 'Test Stock Valuation',
            'code': 'TSTVAL',
            'account_type': 'asset_current',
            'company_ids': company_ids,
        })
        cls.acc_input = Account.create({
            'name': 'Test Stock Input',
            'code': 'TSTIN',
            'account_type': 'asset_current',
            'company_ids': company_ids,
        })
        cls.acc_output = Account.create({
            'name': 'Test Stock Output',
            'code': 'TSTOUT',
            'account_type': 'asset_current',
            'company_ids': company_ids,
        })
        cls.acc_expense = Account.create({
            'name': 'Test COGS',
            'code': 'TSTCOGS',
            'account_type': 'expense',
            'company_ids': company_ids,
        })
        cls.journal = cls.env['account.journal'].create({
            'name': 'Test Stock Journal',
            'code': 'TSTSJ',
            'type': 'general',
        })

        cls.categ = cls.env['product.category'].create({
            'name': 'Test AVCO Real Time',
            'property_cost_method': 'average',
            'property_valuation': 'real_time',
            'property_stock_valuation_account_id': cls.acc_valuation.id,
            'property_stock_account_input_categ_id': cls.acc_input.id,
            'property_stock_account_output_categ_id': cls.acc_output.id,
            'property_stock_journal': cls.journal.id,
            'property_account_expense_categ_id': cls.acc_expense.id,
        })

        cls.product = cls.env['product.product'].create({
            'name': 'Kardex Audit Product',
            'type': 'consu',
            'is_storable': True,
            'categ_id': cls.categ.id,
        })

    def _svl(self, day, qty, unit_cost, value, product=None):
        return self.env['stock.valuation.layer'].create({
            'company_id': self.company.id,
            'product_id': (product or self.product).id,
            'quantity': qty,
            'unit_cost': unit_cost,
            'value': value,
            'accounting_date': datetime(2026, 1, day, 8, 0, 0),
        })

    def _new_audit(self):
        return self.env['stock.kardex.cost.audit'].create({
            'company_id': self.company.id,
            'date_from': fields.Date.to_date('2026-01-01'),
            'date_to': fields.Date.to_date('2026-01-31'),
            'date_basis': 'accounting',
            'only_differences': True,
            'correction_date': fields.Date.to_date('2026-01-31'),
        })

    def test_audit_recompute_and_regularize(self):
        # IN 10 @ 10 = 100 ; OUT 5 booked at 40 (recorded COGS) while the WAC
        # COGS should be 5 * 10 = 50. Recorded balance = 60, WAC balance = 50.
        self._svl(5, 10, 10, 100.0)
        self._svl(10, -5, 8, -40.0)

        audit = self._new_audit()
        audit.action_compute()
        self.assertEqual(len(audit.line_ids), 1, "the product with a gap must be listed")
        line = audit.line_ids
        self.assertTrue(line.has_difference)
        self.assertAlmostEqual(line.value_recorded, 60.0, places=2)
        self.assertAlmostEqual(line.value_wac, 50.0, places=2)
        self.assertAlmostEqual(line.value_difference, 10.0, places=2)
        self.assertEqual(line.correction_state, 'pending')

        # --- Recompute valuation ---
        audit.action_recompute_valuation()
        svl = line.revaluation_svl_id
        self.assertTrue(svl, "a correction layer must be created")
        self.assertTrue(svl.kardex_cost_correction)
        self.assertEqual(svl.quantity, 0)
        self.assertAlmostEqual(svl.value, -10.0, places=2)
        self.assertEqual(line.correction_state, 'revalued')

        # The recomputed cost (value_wac / qty_balance = 50 / 5) is propagated
        # to the product so future moves are valued correctly.
        self.assertAlmostEqual(self.product.standard_price, 10.0, places=2)
        # The cost-change log snapshots the corrected price on the layer.
        self.assertAlmostEqual(svl.standard_price, 10.0, places=2)

        # The recorded valuation now equals the WAC: a fresh audit converges.
        audit2 = self._new_audit()
        audit2.action_compute()
        self.assertFalse(
            audit2.line_ids,
            "after recomputing, the recorded value matches the kardex (no diff)")

        # Idempotency: re-running does not create a second layer.
        before = self.env['stock.valuation.layer'].search_count([
            ('product_id', '=', self.product.id),
            ('kardex_cost_correction', '=', True),
        ])
        line.action_line_recompute()
        after = self.env['stock.valuation.layer'].search_count([
            ('product_id', '=', self.product.id),
            ('kardex_cost_correction', '=', True),
        ])
        self.assertEqual(before, after, "recompute must be idempotent")

        # --- Regularize entries ---
        audit.action_regularize_entries()
        move = line.correction_move_id
        self.assertTrue(move, "a correction entry must be created")
        self.assertEqual(move.state, 'draft', "the entry must be left in draft")
        self.assertEqual(move.journal_id, self.journal)
        self.assertEqual(move.stock_valuation_layer_ids, svl)

        # added_value is -10 -> credit valuation / debit COGS for 10.
        debit_line = move.line_ids.filtered(lambda l: l.debit)
        credit_line = move.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(debit_line.account_id, self.acc_expense)
        self.assertEqual(credit_line.account_id, self.acc_valuation)
        self.assertAlmostEqual(debit_line.debit, 10.0, places=2)
        self.assertAlmostEqual(credit_line.credit, 10.0, places=2)

        # Idempotency on regularize too.
        line.action_line_regularize()
        self.assertEqual(
            self.env['account.move'].search_count([
                ('stock_valuation_layer_ids', '=', svl.id)]),
            1, "regularize must not duplicate the entry")
        self.assertEqual(line.correction_state, 'regularized')

    def test_non_avco_products_are_excluded(self):
        """Only weighted-average products are auditable: the recorded-vs-WAC
        comparison is meaningless for standard and FIFO costing."""
        std_categ = self.env['product.category'].create({
            'name': 'Test Standard',
            'property_cost_method': 'standard',
            'property_valuation': 'manual_periodic',
        })
        fifo_categ = self.env['product.category'].create({
            'name': 'Test FIFO',
            'property_cost_method': 'fifo',
            'property_valuation': 'manual_periodic',
        })
        std_product = self.env['product.product'].create({
            'name': 'Standard Product', 'type': 'consu',
            'is_storable': True, 'categ_id': std_categ.id,
        })
        fifo_product = self.env['product.product'].create({
            'name': 'FIFO Product', 'type': 'consu',
            'is_storable': True, 'categ_id': fifo_categ.id,
        })
        # Same gap pattern as the AVCO product, for each non-AVCO product.
        for product in (std_product, fifo_product):
            self._svl(5, 10, 10, 100.0, product=product)
            self._svl(10, -5, 8, -40.0, product=product)
        # And one genuine AVCO product so the audit is not empty.
        self._svl(5, 10, 10, 100.0)
        self._svl(10, -5, 8, -40.0)

        audit = self._new_audit()
        audit.action_compute()
        audited = audit.line_ids.product_id
        self.assertIn(self.product, audited, "the AVCO product must be audited")
        self.assertNotIn(std_product, audited, "standard-cost products are excluded")
        self.assertNotIn(fifo_product, audited, "FIFO products are excluded")
