from unittest.mock import patch

from odoo.tests import tagged

from .common import TestExpenseSettlementCommon


@tagged('post_install', '-at_install')
class TestExpenseAutoSettlement(TestExpenseSettlementCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.hr_expense_auto_settle = True

    def test_bills_are_settled_when_posted(self):
        """Caso de la nota técnica: anticipo 500, dos comprobantes por 700 en total."""
        advance = self.create_advance(500.0, date='2022-01-05')
        bills = self.approve_and_post(self.create_sheet([
            self.receipt_values(400.0, number='1'),
            self.receipt_values(300.0, vendor=self.vendor_2, number='2'),
        ]))

        self.assertEqual(len(bills), 2)
        self.assertTrue(all(bill.payment_state == 'paid' for bill in bills))
        self.assertTrue(advance.reconciled)
        settlements = bills.hr_expense_settlement_move_ids
        self.assertEqual(len(settlements), 2)
        self.assertEqual(set(settlements.mapped('date')), set(bills.mapped('date')), 'En la fecha contable de cada factura')
        open_lines = settlements.line_ids.filtered(lambda line: line.account_id == self.advance_account and not line.reconciled)
        self.assertAlmostEqual(sum(open_lines.mapped('amount_residual')), -200.0, msg='Lo no cubierto queda a favor del empleado')
        sheet = bills.expense_sheet_id
        self.assertEqual(sheet.payment_state, 'paid')
        self.assertEqual(sheet.state, 'done')

    def test_manual_post_of_a_bill_is_settled(self):
        self.create_advance(100.0)
        sheet = self.create_sheet([self.receipt_values(100.0)])
        sheet.action_submit_sheet()
        sheet.action_approve_expense_sheets()
        bill = sheet.account_move_ids
        self.assertEqual(bill.state, 'draft')

        bill.action_post()
        self.assertEqual(bill.payment_state, 'paid')

    def test_disabled_or_not_configured_company_is_not_settled(self):
        self.create_advance(100.0)
        self.company.hr_expense_auto_settle = False
        bill = self.create_receipt_bill(100.0, number='1')
        self.assertEqual(bill.payment_state, 'not_paid')
        self.assertFalse(bill.hr_expense_settlement_move_ids)

        self.company.write({'hr_expense_auto_settle': True, 'hr_expense_settlement_journal_id': False})
        # Otro monto: con el mismo, la detección nativa de duplicados no aprueba el informe.
        bill = self.create_receipt_bill(101.0, number='2')
        self.assertEqual(bill.payment_state, 'not_paid')
        self.assertTrue(bill.hr_expense_can_settle, 'Queda disponible el botón manual')

    def test_failure_keeps_the_bill_posted_and_explains_why(self):
        # Sin anticipos ni cuentas de entregas a rendir no hay dónde dejar el saldo del empleado.
        self.company.hr_expense_advance_account_ids = False
        Company = type(self.env['res.company'])
        with patch.object(Company, '_get_hr_expense_advance_accounts', lambda company: self.env['account.account']):
            bill = self.create_receipt_bill(100.0)

        self.assertEqual(bill.state, 'posted')
        self.assertEqual(bill.payment_state, 'not_paid')
        self.assertFalse(bill.hr_expense_settlement_move_ids)
        self.assertIn('No se pudo liquidar automáticamente', bill.message_ids[0].body)

    def test_regular_vendor_bills_are_not_settled(self):
        self.create_advance(100.0)
        bill = self.init_invoice('in_invoice', partner=self.vendor, amounts=[100.0], post=True)
        self.assertEqual(bill.payment_state, 'not_paid')
        self.assertFalse(bill.hr_expense_settlement_move_ids)
