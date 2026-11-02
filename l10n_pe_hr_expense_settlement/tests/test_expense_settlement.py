from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import TestExpenseSettlementCommon


@tagged('post_install', '-at_install')
class TestExpenseSettlement(TestExpenseSettlementCommon):

    def assert_settlement(self, bill, expected_lines):
        settlement = bill.hr_expense_settlement_move_ids
        self.assertEqual(len(settlement), 1)
        self.assertEqual(settlement.state, 'posted')
        self.assertEqual(settlement.journal_id, self.company_data['default_journal_misc'])
        self.assertRecordValues(settlement.line_ids.sorted('balance', reverse=True), expected_lines)
        return settlement

    # -------------------------------------------------------------------------
    # Botón y anticipos visibles
    # -------------------------------------------------------------------------

    def test_button_only_for_open_expense_bills(self):
        bill = self.create_receipt_bill(100.0)
        self.assertTrue(bill.hr_expense_can_settle)

        regular_bill = self.init_invoice('in_invoice', partner=self.vendor, amounts=[100.0], post=True)
        self.assertFalse(regular_bill.hr_expense_can_settle)

        # Otro monto: el control nativo de gastos duplicados no detiene la aprobación.
        draft_bill = self.create_sheet([self.receipt_values(90.0, number='2')])
        draft_bill.action_submit_sheet()
        draft_bill.action_approve_expense_sheets()
        self.assertEqual(draft_bill.account_move_ids.state, 'draft')
        self.assertFalse(draft_bill.account_move_ids.hr_expense_can_settle)

    def test_advance_lines_shared_with_employee_tab(self):
        advance = self.create_advance(500.0)
        other_employee_advance = self.create_advance(300.0, partner=self.partner_b)
        other_account_line = self.init_invoice('out_invoice', partner=self.employee_partner, amounts=[50.0], post=True)
        bill = self.create_receipt_bill(100.0)

        self.assertEqual(bill.expense_employee_account14_line_ids, advance)
        self.assertNotIn(other_employee_advance, bill.expense_employee_account14_line_ids)
        self.assertFalse(bill.expense_employee_account14_line_ids & other_account_line.line_ids)

    def test_advance_accounts_default_to_account_14_prefix(self):
        self.company.hr_expense_advance_account_ids = [Command.clear()]
        prefixed = self.env['account.account'].create({
            'code': '141399', 'name': 'Entregas a rendir ME', 'account_type': 'asset_receivable', 'reconcile': True,
        })
        accounts = self.company._get_hr_expense_advance_accounts()
        self.assertIn(prefixed, accounts)
        self.assertIn(self.advance_account, accounts)
        self.assertTrue(all(account.code.startswith('14') and account.reconcile for account in accounts))

    # -------------------------------------------------------------------------
    # Liquidación en la moneda de la compañía
    # -------------------------------------------------------------------------

    def test_full_settlement(self):
        advance = self.create_advance(700.0)
        bill = self.create_receipt_bill(700.0)
        sheet = bill.expense_sheet_id

        wizard = self.open_settlement_wizard(bill)
        self.assertEqual(wizard.journal_id, self.company_data['default_journal_misc'])
        self.assertEqual(wizard.line_ids.advance_line_id, advance)
        self.assertEqual(wizard.amount, 700.0)
        self.assertEqual(wizard.excess_amount, 0.0)
        wizard.action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        self.assertTrue(advance.reconciled)
        payable = bill.line_ids.filtered(lambda line: line.account_id.account_type == 'liability_payable')
        self.assert_settlement(bill, [
            {'account_id': payable.account_id.id, 'partner_id': self.vendor.id, 'balance': 700.0, 'reconciled': True},
            {'account_id': self.advance_account.id, 'partner_id': self.employee_partner.id, 'balance': -700.0, 'reconciled': True},
        ])
        self.assertEqual(bill.hr_expense_settlement_count, 1)
        self.assertEqual(sheet.payment_state, 'paid')
        self.assertEqual(sheet.state, 'done')
        self.assertFalse(bill.hr_expense_can_settle)
        self.assertIn('Liquidación de rendición', bill.message_ids[0].body)
        self.assertIn('Liquidación de rendición', sheet.message_ids[0].body)

    def test_always_settles_the_whole_bill(self):
        """Anticipo 500, rendido 700: se cancela toda la factura y los 200 que no
        cubre el anticipo quedan a favor del empleado (nunca deuda al proveedor)."""
        advance = self.create_advance(500.0)
        bill = self.create_receipt_bill(700.0)

        wizard = self.open_settlement_wizard(bill)
        self.assertEqual(wizard.amount, 700.0)
        self.assertEqual(wizard.selected_advance_amount, 500.0)
        self.assertEqual(wizard.excess_amount, 200.0)
        self.assertEqual(wizard.excess_account_id, self.advance_account)
        wizard.action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        self.assertTrue(advance.reconciled)
        reimbursement = bill.hr_expense_settlement_move_ids.line_ids.filtered(
            lambda line: line.account_id == self.advance_account and not line.reconciled
        )
        self.assertRecordValues(reimbursement, [{'partner_id': self.employee_partner.id, 'amount_residual': -200.0}])

    def test_without_advances_the_whole_bill_is_reimbursed(self):
        bill = self.create_receipt_bill(300.0)
        wizard = self.open_settlement_wizard(bill)
        self.assertFalse(wizard.line_ids)
        self.assertEqual(wizard.excess_amount, 300.0)
        wizard.action_confirm()
        self.assertEqual(bill.payment_state, 'paid')

    def test_excess_in_a_single_settlement(self):
        """Caso de la nota técnica: anticipo 500, comprobante 700."""
        advance = self.create_advance(500.0)
        bill = self.create_receipt_bill(700.0)

        wizard = self.open_settlement_wizard(bill)
        self.assertEqual(wizard.excess_amount, 200.0)
        wizard.action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        self.assertTrue(advance.reconciled)
        self.assert_settlement(bill, [
            {'partner_id': self.vendor.id, 'balance': 700.0, 'amount_residual': 0.0},
            {'partner_id': self.employee_partner.id, 'balance': -200.0, 'amount_residual': -200.0},
            {'partner_id': self.employee_partner.id, 'balance': -500.0, 'amount_residual': 0.0},
        ])

    def test_advance_bigger_than_bill_stays_open(self):
        advance = self.create_advance(1000.0)
        bill = self.create_receipt_bill(600.0)

        self.open_settlement_wizard(bill).action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        self.assertFalse(advance.reconciled)
        self.assertEqual(advance.amount_residual, 400.0)

    def test_several_advances_are_applied_oldest_first(self):
        old_advance = self.create_advance(300.0, date='2022-01-05')
        new_advance = self.create_advance(500.0, date='2022-01-20')
        bill = self.create_receipt_bill(600.0)

        wizard = self.open_settlement_wizard(bill)
        self.assertEqual(wizard.amount, 600.0)
        self.assertEqual(wizard.line_ids.mapped('applied_amount'), [300.0, 300.0])
        wizard.action_confirm()

        self.assertTrue(old_advance.reconciled)
        self.assertEqual(new_advance.amount_residual, 200.0)
        self.assertEqual(bill.payment_state, 'paid')

    def test_unselected_advance_is_not_touched(self):
        old_advance = self.create_advance(300.0, date='2022-01-05')
        new_advance = self.create_advance(500.0, date='2022-01-20')
        bill = self.create_receipt_bill(400.0)

        with Form(self.env['hr.expense.settlement.wizard'].with_context(default_move_id=bill.id)) as wizard_form:
            wizard_form.date = self.today
            with wizard_form.line_ids.edit(0) as line_form:
                line_form.selected = False
            self.assertEqual(wizard_form.amount, 400.0)
            self.assertEqual(wizard_form.selected_advance_amount, 500.0)
        wizard_form.record.action_confirm()

        self.assertEqual(old_advance.amount_residual, 300.0)
        self.assertEqual(new_advance.amount_residual, 100.0)
        self.assertEqual(bill.payment_state, 'paid')

    # -------------------------------------------------------------------------
    # Multimoneda
    # -------------------------------------------------------------------------

    def test_foreign_bill_does_not_use_company_currency_advance(self):
        """E1: un comprobante en moneda extranjera no consume un fondo en la moneda
        de la compañía; queda a reembolsar en la cuenta de su moneda."""
        foreign_account = self.env['account.account'].create({
            'code': '141301', 'name': 'Entregas a rendir M.E.', 'account_type': 'asset_receivable',
            'reconcile': True, 'currency_id': self.other_currency.id,
        })
        self.company.hr_expense_advance_account_ids = [Command.link(foreign_account.id)]
        advance = self.create_advance(50.0)
        bill = self.create_receipt_bill(100.0, currency_id=self.other_currency.id)

        wizard = self.open_settlement_wizard(bill)
        self.assertFalse(wizard.line_ids.selected)
        self.assertEqual(wizard.excess_account_id, foreign_account)
        wizard.action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        self.assertFalse(advance.reconciled)
        self.assertEqual(advance.amount_residual, 50.0)

    def test_foreign_bill_with_company_currency_advance_chosen_manually(self):
        # 1 USD (compañía) = 2 HRK
        advance = self.create_advance(50.0)
        bill = self.create_receipt_bill(100.0, currency_id=self.other_currency.id)

        wizard = self.open_settlement_wizard(bill)
        wizard.line_ids.selected = True
        self.assertEqual(wizard.line_ids.available_amount, 100.0)
        self.assertEqual(wizard.amount, 100.0)
        wizard.action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        self.assertTrue(advance.reconciled)
        self.assert_settlement(bill, [
            {'currency_id': self.other_currency.id, 'amount_currency': 100.0, 'balance': 50.0},
            {'currency_id': self.company.currency_id.id, 'amount_currency': -50.0, 'balance': -50.0},
        ])

    def test_company_currency_bill_with_foreign_advance_chosen_manually(self):
        advance = self.create_advance(40.0, currency=self.other_currency, amount_currency=80.0)
        bill = self.create_receipt_bill(40.0)

        wizard = self.open_settlement_wizard(bill)
        self.assertFalse(wizard.line_ids.selected, 'Por defecto solo se aplican anticipos de la misma moneda')
        wizard.line_ids.selected = True
        self.assertEqual(wizard.line_ids.available_amount, 40.0)
        wizard.action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        self.assertTrue(advance.reconciled)

    def test_foreign_rate_difference_goes_to_exchange_difference(self):
        """Anticipo en HRK a 1 USD = 2 HRK; la liquidación se hace cuando 1 USD = 4 HRK:
        la conciliación nativa genera la diferencia de cambio del anticipo."""
        self.env['res.currency.rate'].create({
            'name': '2022-01-20', 'rate': 4.0, 'currency_id': self.other_currency.id, 'company_id': self.company.id,
        })
        advance = self.create_advance(50.0, date='2022-01-10', currency=self.other_currency, amount_currency=100.0)
        bill = self.create_receipt_bill(100.0, currency_id=self.other_currency.id)

        wizard = self.open_settlement_wizard(bill)
        self.assertEqual(wizard.line_ids.available_amount, 100.0)
        wizard.action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        self.assertTrue(advance.reconciled)
        exchange_move = advance.matched_credit_ids.exchange_move_id
        self.assertTrue(exchange_move, 'La diferencia de cambio la registra la conciliación nativa.')
        self.assertEqual(exchange_move.journal_id, self.company.currency_exchange_journal_id)
        self.assertAlmostEqual(advance.amount_residual, 0.0)

    # -------------------------------------------------------------------------
    # Validaciones y multicompañía
    # -------------------------------------------------------------------------

    def test_amount_is_the_bill_residual(self):
        self.create_advance(1000.0)
        bill = self.create_receipt_bill(600.0)
        wizard = self.open_settlement_wizard(bill)
        self.assertEqual(wizard.amount, bill.amount_residual)
        self.assertTrue(wizard._fields['amount'].related, 'El monto no es editable: siempre es el saldo de la factura')

    def test_excess_requires_account(self):
        self.company.hr_expense_advance_account_ids = [Command.clear()]
        with patch.object(type(self.company), '_get_hr_expense_advance_accounts', return_value=self.env['account.account']):
            wizard = self.open_settlement_wizard(self.create_receipt_bill(600.0))
        self.assertFalse(wizard.excess_account_id)
        with self.assertRaisesRegex(UserError, 'cuenta'):
            wizard.action_confirm()

    def test_settled_bill_cannot_be_settled_twice(self):
        self.create_advance(600.0)
        bill = self.create_receipt_bill(600.0)
        wizard = self.open_settlement_wizard(bill)
        self.open_settlement_wizard(bill).action_confirm()
        with self.assertRaisesRegex(UserError, 'ya no tiene saldo'):
            wizard.action_confirm()

    def test_advances_of_other_company_are_ignored(self):
        company_2 = self.company_data_2['company']
        advance_account_2 = self.env['account.account'].with_company(company_2).create({
            'code': '141300', 'name': 'Entregas a rendir', 'account_type': 'asset_receivable', 'reconcile': True,
        })
        advance_2 = self.env['account.move'].with_company(company_2).create({
            'move_type': 'entry',
            'date': self.today,
            'journal_id': self.company_data_2['default_journal_misc'].id,
            'line_ids': [
                Command.create({'account_id': advance_account_2.id, 'partner_id': self.employee_partner.id, 'balance': 300.0}),
                Command.create({'account_id': self.company_data_2['default_journal_bank'].default_account_id.id, 'balance': -300.0}),
            ],
        })
        advance_2.action_post()
        # La compañía 1 también usa el prefijo 14 por defecto: debe filtrar por compañía.
        self.company.hr_expense_advance_account_ids = [Command.clear()]
        own_advance = self.create_advance(100.0)
        bill = self.create_receipt_bill(300.0)

        self.assertEqual(self.open_settlement_wizard(bill).line_ids.advance_line_id, own_advance)
        self.assertEqual(bill.expense_employee_account14_line_ids, own_advance)

    def test_unreconcile_settlement_reopens_bill(self):
        advance = self.create_advance(300.0)
        bill = self.create_receipt_bill(300.0)
        self.open_settlement_wizard(bill).action_confirm()

        bill.hr_expense_settlement_move_ids.button_draft()

        self.assertEqual(bill.payment_state, 'not_paid')
        self.assertFalse(advance.reconciled)
        self.assertTrue(bill.hr_expense_can_settle)

    def test_excess_respects_account_currency(self):
        """La cuenta de entregas a rendir M.E. solo admite su moneda: el exceso se
        registra en esa moneda aunque la factura esté en la de la compañía."""
        foreign_account = self.env['account.account'].create({
            'code': '141301', 'name': 'Entregas a rendir M.E.', 'account_type': 'asset_receivable',
            'reconcile': True, 'currency_id': self.other_currency.id,
        })
        bill = self.create_receipt_bill(100.0)
        wizard = self.open_settlement_wizard(bill)
        wizard.excess_account_id = foreign_account
        wizard.action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        excess_line = bill.hr_expense_settlement_move_ids.line_ids.filtered(lambda line: line.account_id == foreign_account)
        self.assertRecordValues(excess_line, [{
            'currency_id': self.other_currency.id, 'amount_currency': -200.0, 'balance': -100.0,
        }])

    def test_employee_tab_hides_canceled_payments(self):
        """Pestaña informativa de je_approval_expense_flow: solo pagos vigentes."""
        def pay_employee(amount):
            payment = self.env['account.payment'].create({
                'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': self.employee_partner.id,
                'amount': amount, 'journal_id': self.company_data['default_journal_bank'].id,
            })
            payment.action_post()
            return payment

        open_payment = pay_employee(100.0)
        canceled_payment = pay_employee(50.0)
        canceled_payment.action_draft()
        canceled_payment.action_cancel()
        bill = self.create_receipt_bill(100.0)

        self.assertIn(open_payment, bill.expense_employee_pending_payment_ids)
        self.assertNotIn(canceled_payment, bill.expense_employee_pending_payment_ids)

    # -------------------------------------------------------------------------
    # Cada línea de la liquidación cancela su propia contrapartida
    # -------------------------------------------------------------------------

    def matched_lines(self, line):
        return (line.matched_debit_ids.debit_move_id | line.matched_credit_ids.credit_move_id) - line

    def test_advance_is_reconciled_with_its_own_line(self):
        """Caso de staging LREND/2026/09/0002: el anticipo se cruzaba con la línea
        del exceso y la línea que lo aplicaba quedaba abierta."""
        applied_advance = self.create_advance(30.0, date='2022-01-05')
        skipped_advance = self.create_advance(20.0, date='2022-01-10')
        bill = self.create_receipt_bill(80.06)

        wizard = self.open_settlement_wizard(bill)
        wizard.line_ids.filtered(lambda l: l.advance_line_id == skipped_advance).selected = False
        wizard.action_confirm()

        lines = bill.hr_expense_settlement_move_ids.line_ids
        apply_line = lines.filtered(lambda l: 'aplica anticipo' in l.name)
        excess_line = lines.filtered(lambda l: 'saldo a reembolsar' in l.name)
        self.assertTrue(apply_line.reconciled)
        self.assertEqual(self.matched_lines(apply_line), applied_advance)
        self.assertFalse(excess_line.matched_debit_ids, 'El exceso no se cruza con ningún anticipo')
        self.assertAlmostEqual(excess_line.amount_residual, -50.06)
        self.assertEqual(skipped_advance.amount_residual, 20.0)

    def test_each_advance_is_reconciled_with_its_line(self):
        old_advance = self.create_advance(300.0, date='2022-01-05')
        new_advance = self.create_advance(500.0, date='2022-01-20')
        bill = self.create_receipt_bill(900.0)

        self.open_settlement_wizard(bill).action_confirm()

        lines = bill.hr_expense_settlement_move_ids.line_ids
        for advance in (old_advance, new_advance):
            line = lines.filtered(lambda l: advance.move_id.name in (l.name or ''))
            self.assertEqual(self.matched_lines(line), advance)
        self.assertAlmostEqual(lines.filtered(lambda l: 'saldo a reembolsar' in l.name).amount_residual, -100.0)
