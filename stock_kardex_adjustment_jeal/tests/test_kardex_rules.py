# -*- coding: utf-8 -*-
from datetime import date

from odoo import Command, fields
from odoo.tests import tagged

from .test_kardex_adjustment import KardexAdjustmentCommon


@tagged('post_install', '-at_install')
class TestKardexRules(KardexAdjustmentCommon):
    """Reglas de la nota de compras, devoluciones, fabricaciones y desmontajes."""

    def _lines(self, adjustment_type=None):
        lines = self._posted_lines()
        return lines.filtered(lambda l: l.adjustment_type == adjustment_type) if adjustment_type else lines

    def _counterpart(self, line):
        valuation = self.valuation_account
        return line.move_id.line_ids.filtered(lambda l: l.account_id != valuation).account_id

    # ------------------------------------------------------------------
    # R7: contrapartida del ajuste de costo
    # ------------------------------------------------------------------
    def test_sale_with_order_against_cogs(self):
        """Venta con orden de venta: el ajuste de costo va contra la cuenta de
        costo de ventas de ajustes (6912100)."""
        self._move(10, 100, date(2026, 1, 2))
        out = self._move(-5, entry_date=date(2026, 1, 20))
        self._move(10, 130, date(2026, 1, 10))
        order = self.env['sale.order'].create({
            'partner_id': self.partner_a.id,
            'order_line': [Command.create({'product_id': self.product.id, 'product_uom_qty': 5})],
        })
        out.sale_line_id = order.order_line
        self._run().action_generate()
        line = self._lines('cost')
        self.assertEqual(line.counterpart_account_id, self.cogs_account)
        self.assertEqual(self._counterpart(line), self.cogs_account)

    # ------------------------------------------------------------------
    # R1: devolución a proveedor
    # ------------------------------------------------------------------
    def test_vendor_return_at_origin_cost_against_input_account(self):
        """La devolución sale al costo de su recepción (100), no al promedio
        (115), y la diferencia va contra la cuenta de entrada (61)."""
        receipt = self._move(10, 100, date(2026, 1, 2))
        self._move(10, 130, date(2026, 1, 3))
        back = self.env['stock.move'].create({
            'name': 'devolución',
            'product_id': self.product.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.supplier_location.id,
            'product_uom': self.product.uom_id.id,
            'product_uom_qty': 10,
            'origin_returned_move_id': receipt.id,
        })
        back._action_confirm()
        back._action_assign()
        back.quantity = 10
        back.picked = True
        back._action_done()
        self._set_entry_date(back, date(2026, 1, 5))
        self.assertAlmostEqual(back.stock_valuation_layer_ids.value, -1150.0)
        run = self._run()
        run.action_compute()
        row = run.adjustment_row_ids
        self.assertEqual(row.adj_type, 'return')
        # La contrapartida se ve en el kardex antes de registrar
        self.assertEqual(row.counterpart_account_id, self.categ.property_stock_account_input_categ_id)
        run.action_generate()
        line = self._lines('return')
        self.assertAlmostEqual(line.amount, 150.0)
        self.assertEqual(line.adjusted_layer_id, back.stock_valuation_layer_ids.filtered('quantity'))
        self.assertEqual(self._counterpart(line), self.categ.property_stock_account_input_categ_id)
        self.assertEqual(line.move_id.kardex_adjustment_type, 'return')
        # Queda la segunda recepción, a su costo
        self.assertAlmostEqual(self.product.value_svl, 1300.0)
        self.assertFalse(self._lines('cost'))

    # ------------------------------------------------------------------
    # R3, R5 y R6: factura vs recepción
    # ------------------------------------------------------------------
    def _usd_purchase(self, purchase_method):
        currency = self.setup_other_currency('EUR', rates=[
            ('2025-01-01', 0.5),                          # 1 EUR = 2.00
            (fields.Date.to_string(fields.Date.today()), 0.4),  # 1 EUR = 2.50 al recibir
        ])
        self.product.purchase_method = purchase_method
        order = self.env['purchase.order'].create({
            'partner_id': self.partner_a.id,
            'currency_id': currency.id,
            'picking_type_id': self.warehouse.in_type_id.id,
            'order_line': [Command.create({
                'product_id': self.product.id, 'product_qty': 10, 'price_unit': 100, 'taxes_id': False,
            })],
        })
        order.button_confirm()
        return order

    def _bill(self, order, invoice_date):
        order.action_create_invoice()
        bill = order.invoice_ids
        bill.write({'invoice_date': invoice_date, 'date': invoice_date})
        bill.action_post()
        return bill

    def _receive(self, order, entry_date):
        picking = order.picking_ids
        picking.move_ids.quantity = 10
        picking.move_ids.picked = True
        picking.button_validate()
        self._set_entry_date(picking.move_ids, entry_date)
        return picking.move_ids

    def test_invoice_before_receipt_exchange_difference(self):
        """Factura a 2.00 (2,000) antes de recibir a 2.50 (2,500): ajuste de
        cambio -500 con la fecha de la recepción, contra la 61 por el
        complementario."""
        order = self._usd_purchase('purchase')
        bill = self._bill(order, date(2026, 1, 5))
        receipt = self._receive(order, date(2026, 1, 10))
        # Odoo estándar valoriza la recepción ya facturada al tipo de cambio de
        # la factura; en jeal entra al de la recepción (2.50)
        receipt.stock_valuation_layer_ids.sudo().value = 2500.0
        run = self._run()
        run.action_compute()
        self.assertAlmostEqual(run.fx_adjust_total, -500.0)
        self.assertAlmostEqual(run.price_adjust_total, 0.0)
        run.action_generate()
        line = self._lines('fx')
        self.assertEqual(len(line), 1)
        self.assertEqual(line.invoice_id, bill)
        self.assertEqual(line.date, date(2026, 1, 10))
        self.assertAlmostEqual(line.amount, -500.0)
        self.assertEqual(line.fx_move_id.kardex_adjustment_type, 'fx_61')
        input_account = self.categ.property_stock_account_input_categ_id
        self.assertIn(input_account, line.fx_move_id.line_ids.account_id)
        # 60 = 61: el inventario queda al valor facturado
        self.assertAlmostEqual(self.product.value_svl, 2000.0)
        # Reproceso: nada pendiente
        again = self._run()
        again.action_compute()
        self.assertEqual(again.pending_count, 0)

    def test_invoice_after_receipt_not_duplicated(self):
        """Factura posterior a la recepción: lo que Odoo ya llevó con la
        diferencia de precio no se vuelve a ajustar; el inventario queda al
        valor facturado."""
        order = self._usd_purchase('receive')
        self._receive(order, date(2026, 1, 3))
        self._bill(order, date(2026, 1, 5))
        price_diff = self.env['stock.valuation.layer'].search([
            ('product_id', '=', self.product.id), ('account_move_line_id', '!=', False)])
        # Odoo lleva la diferencia con un asiento de la fecha en que se publica
        # la factura en el sistema, posterior al período
        self.assertAlmostEqual(price_diff.value, -500.0)
        self.assertGreater(price_diff.account_move_id.date, date(2026, 1, 31))
        run = self._run()
        run.action_generate()
        self.assertFalse(self._lines('fx') | self._lines('price'))
        self.assertAlmostEqual(self.product.value_svl, 2000.0)
        again = self._run()
        again.action_compute()
        self.assertEqual(again.pending_count, 0)
        self.assertFalse(self._lines('cost'))
