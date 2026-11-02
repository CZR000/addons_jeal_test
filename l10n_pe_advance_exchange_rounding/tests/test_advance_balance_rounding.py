from odoo import Command
from odoo.tests import tagged

from odoo.addons.l10n_pe_advance_global_discount.tests.data_invoices import F001_1457
from odoo.addons.l10n_pe_advance_global_discount.tests.test_advance_rounding import AdvanceInvoiceCommon

# F001-00001491 de EQUIPAMIENTO (USD a 3.36): en soles las ventas suman
# 6,832.62 y el anticipo 6,832.63; la cuenta 12 quedaba con 0.01 e importe en
# divisa 0.00.
F001_1491 = {
    'lines': [(76.0, 8.457), (30.0, 5.99), (20.0, 1.233), (6.0, 4.228), (50.0, 12.65), (8.0, 31.361),
              (8.0, 21.142), (8.0, 10.924), (30.0, 0.599), (10.0, 0.317)],
    'advance': 2033.52,
    'advance_invoice': 'F001-1480',
}


@tagged('post_install', '-at_install', 'post_install_l10n')
class TestAdvanceBalanceRounding(AdvanceInvoiceCommon):
    """Factura saldada al 100 % con anticipo: la conversión a soles de cada
    línea no debe dejar céntimos en la cuenta por cobrar."""

    def natural_balance(self, line):
        """Conversión nativa de Odoo: precio sin redondear por el cambio."""
        return round(line.move_id.direction_sign * line.quantity * line.price_unit * 3.36, 2)

    def assert_no_receivable_cents(self, invoice):
        self.assertFalse(invoice.line_ids.filtered(lambda l: l.display_type == 'payment_term'),
                         'Factura en cero: sin línea por cobrar')
        self.assertFalse(invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable'))
        self.assertTrue(invoice.company_currency_id.is_zero(sum(invoice.line_ids.mapped('balance'))))

    def test_real_case_had_residual(self):
        """Sin el ajuste, las ventas en soles no cuadran con el anticipo."""
        invoice = self.create_invoice(F001_1491)
        products = invoice.invoice_line_ids.filtered(lambda l: not l.product_id.l10n_pe_advance)
        self.assertAlmostEqual(sum(self.natural_balance(line) for line in products), -6832.62)
        self.assertAlmostEqual(sum(products.mapped('balance')), -6832.62, msg='Las ventas no cambian')

    def test_full_advance_leaves_no_cents_in_receivable(self):
        for company_rounding in ('round_per_line', 'round_globally'):
            for case in (F001_1491, F001_1457):
                with self.subTest(rounding=company_rounding, advance=case['advance']):
                    self.company.tax_calculation_rounding_method = company_rounding
                    invoice = self.create_invoice(case)
                    self.assertEqual(invoice.amount_total, 0.0)
                    self.assertEqual(invoice.payment_state, 'paid')
                    self.assert_no_receivable_cents(invoice)
                    advance_line = invoice.invoice_line_ids.filtered('product_id.l10n_pe_advance')
                    self.assertLessEqual(abs(advance_line.balance - self.natural_balance(advance_line)), 0.05)

    def test_partial_advance_keeps_native_conversion(self):
        invoice = self.create_invoice(F001_1491, advance=1000.0)
        advance_line = invoice.invoice_line_ids.filtered('product_id.l10n_pe_advance')
        self.assertAlmostEqual(advance_line.balance, self.natural_balance(advance_line))
        self.assertTrue(invoice.amount_total)

    def test_draft_edit_restores_native_conversion(self):
        """Si se agrega una línea a la factura saldada, el anticipo vuelve a su
        conversión normal; al quitarla, vuelve a absorber el céntimo."""
        invoice = self.create_invoice(F001_1491)
        advance_line = invoice.invoice_line_ids.filtered('product_id.l10n_pe_advance')
        self.assertAlmostEqual(advance_line.balance, 6832.62)
        invoice.button_draft()
        invoice.invoice_line_ids = [Command.create({
            'product_id': self.product.id, 'quantity': 1, 'price_unit': 10.0, 'tax_ids': [Command.set(self.tax_igv.ids)],
        })]
        self.assertAlmostEqual(advance_line.balance, 6832.63)
        invoice.invoice_line_ids.filtered(lambda l: l.price_unit == 10.0).unlink()
        self.assertAlmostEqual(advance_line.balance, 6832.62)
        invoice.action_post()
        self.assert_no_receivable_cents(invoice)
