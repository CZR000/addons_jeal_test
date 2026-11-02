from odoo import Command
from odoo.tests import tagged

from odoo.addons.l10n_pe_advance_global_discount.tests.data_invoices import F001_1295, F001_1449, F001_1457
from odoo.addons.l10n_pe_advance_global_discount.tests.test_advance_rounding import AdvanceInvoiceCommon


@tagged('post_install', '-at_install', 'post_install_l10n')
class TestAdvanceTaxRounding(AdvanceInvoiceCommon):
    """IGV de facturas con anticipo y redondeo de impuestos por línea (caso
    F001-00001507 de EQUIPAMIENTO: base 0.00, IGV 0.02, total 0.02)."""

    def test_full_advance_has_no_tax_with_round_per_line(self):
        """Líneas reales: antes IGV y total 0.04 (F001-1295 y F001-1449)."""
        self.assertEqual(self.company.tax_calculation_rounding_method, 'round_per_line')
        for case in (F001_1295, F001_1449, F001_1457):
            with self.subTest(advance=case['advance_invoice'], lines=len(case['lines'])):
                invoice = self.create_invoice(case)
                self.assertRecordValues(invoice, [{'amount_untaxed': 0.0, 'amount_tax': 0.0, 'amount_total': 0.0}])
                tax_lines = invoice.line_ids.filtered('tax_line_id')
                self.assertTrue(all(invoice.currency_id.is_zero(line.amount_currency) for line in tax_lines))

                values = self.export(invoice)
                self.assertEqual(values['payable'], 0.0)
                self.assertEqual(values['tax'], 0.0)

    def test_line_bases_and_prices_do_not_change(self):
        invoice = self.create_invoice(F001_1449)
        for line in invoice.invoice_line_ids:
            self.assertAlmostEqual(line.price_subtotal, invoice.currency_id.round(line.quantity * line.price_unit))
        self.assertAlmostEqual(sum(invoice.invoice_line_ids.mapped('price_subtotal')), 0.0)

    def test_partial_advance_tax_is_rate_on_net_base(self):
        case = {'lines': [(3.0, 333.33), (7.0, 12.47), (1.0, 0.03), (1.0, 0.03), (1.0, 0.03)], 'advance': 500.0,
                'advance_invoice': 'F001-1500'}
        invoice = self.create_invoice(case)
        net_base = sum(qty * price for qty, price in case['lines']) - case['advance']
        self.assertAlmostEqual(invoice.amount_untaxed, round(net_base, 2))
        self.assertAlmostEqual(invoice.amount_tax, round(round(net_base, 2) * 0.18, 2))
        self.assertAlmostEqual(self.export(invoice)['tax'], invoice.amount_tax)

    def test_invoice_without_advance_keeps_round_per_line(self):
        """Tres líneas de 0.03 (IGV 0.0054 c/u): por línea 0.01 + 0.01 + 0.01."""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id, 'currency_id': self.usd.id,
            'invoice_date': '2026-09-09', 'l10n_latam_document_type_id': self.env.ref('l10n_pe.document_type01').id,
            'invoice_line_ids': [
                Command.create({'product_id': self.product.id, 'quantity': 1, 'price_unit': 0.03, 'tax_ids': [Command.set(self.tax_igv.ids)]})
                for _i in range(3)
            ],
        })
        self.assertAlmostEqual(invoice.amount_tax, 0.03, msg='Sin anticipo no cambia nada (global daría 0.02)')

