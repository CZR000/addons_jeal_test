from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import TestExpenseSettlementCommon


class TestExpenseRenditionCommon(TestExpenseSettlementCommon):
    """Anticipos en moneda extranjera, devoluciones y solicitudes de aprobación."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.hr_expense_auto_settle = True
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.foreign_advance_account = cls.env['account.account'].create({
            'code': '141301',
            'name': 'Personal - Entregas a rendir M.E.',
            'account_type': 'asset_receivable',
            'reconcile': True,
            'currency_id': cls.other_currency.id,
        })
        cls.company.hr_expense_advance_account_ids = [Command.link(cls.foreign_advance_account.id)]
        # Como en OMNI: los diarios de banco cobran y pagan por cuentas puente.
        outstanding = cls.env['account.account'].create({
            'code': '104100', 'name': 'Cobros y pagos pendientes', 'account_type': 'asset_current', 'reconcile': True,
        })
        (cls.bank_journal.inbound_payment_method_line_ids + cls.bank_journal.outbound_payment_method_line_ids).payment_account_id = outstanding
        cls.refund_product = cls.env['product.product'].create({
            'name': 'Devolución de entrega a rendir',
            'can_be_expensed': True,
            'standard_price': 0.0,
            'supplier_taxes_id': [Command.clear()],
            'l10n_pe_is_advance_refund': True,
        })

    def refund_values(self, amount, journal=None, **values):
        return {
            'name': 'Devolución del sobrante',
            'employee_id': self.expense_employee.id,
            'product_id': self.refund_product.id,
            'total_amount_currency': amount,
            'date': self.frozen_today,
            'company_id': self.company.id,
            'currency_id': self.company.currency_id.id,
            'payment_mode': 'own_account',
            'l10n_pe_refund_journal_id': (journal or self.bank_journal).id,
            **values,
        }

    def create_foreign_advance(self, amount_currency, rate=2.0):
        """Anticipo en la cuenta M.E. (1 moneda de la compañía = 2 HRK)."""
        return self.create_advance(
            amount_currency / rate, currency=self.other_currency, amount_currency=amount_currency,
            account=self.foreign_advance_account,
        )

    def register_payment(self, action, journal=None):
        wizard = self.env[action['res_model']].with_context(**action['context']).create({
            'journal_id': (journal or self.bank_journal).id,
        })
        return wizard._create_payments()

    def create_advance_category(self, kind='advance', **values):
        return self.env['approval.category'].create({
            'name': 'Entrega a rendir' if kind == 'advance' else 'Fondo de caja chica',
            'company_id': self.company.id,
            'automated_sequence': True,
            'sequence_code': 'ER/',
            'approval_type': 'payment',
            'has_amount': 'required',
            'default_payment_journal_id': self.bank_journal.id,
            'l10n_pe_advance_kind': kind,
            **values,
        })

    def create_request(self, category, amount, currency=None, **values):
        return self.env['approval.request'].create({
            'category_id': category.id,
            'request_owner_id': self.expense_user_employee.id,
            'amount': amount,
            'l10n_pe_currency_id': (currency or self.company.currency_id).id,
            **values,
        })

    def pay_request(self, request):
        payment = self.env['account.payment'].browse(request._create_and_open_payment()['res_id'])
        payment.action_post()
        return payment



@tagged('post_install', '-at_install')
class TestExpenseRenditionFlow(TestExpenseRenditionCommon):
    """Observaciones de la prueba funcional en OMNI (01/10/2026): E1-E4, M1-M7."""

    # -------------------------------------------------------------------------
    # E1. Cada comprobante se aplica a los anticipos de su moneda
    # -------------------------------------------------------------------------

    def test_receipt_is_applied_to_advances_of_its_currency(self):
        """Fondo en moneda de la compañía (más antiguo) y anticipo en HRK: un
        comprobante en HRK solo consume el anticipo en HRK."""
        local_advance = self.create_advance(500.0, date='2022-01-01')
        foreign_advance = self.create_foreign_advance(200.0)

        bill = self.create_receipt_bill(150.0, currency_id=self.other_currency.id)

        self.assertEqual(bill.payment_state, 'paid')
        self.assertEqual(local_advance.amount_residual, 500.0, 'El fondo en moneda de la compañía no se toca')
        self.assertEqual(foreign_advance.amount_residual_currency, 50.0)

    def test_receipt_without_advance_in_its_currency_is_reimbursed_in_that_currency(self):
        local_advance = self.create_advance(500.0)
        bill = self.create_receipt_bill(150.0, currency_id=self.other_currency.id)

        self.assertEqual(bill.payment_state, 'paid')
        self.assertEqual(local_advance.amount_residual, 500.0)
        excess = bill.hr_expense_settlement_move_ids.line_ids.filtered(
            lambda line: line.account_id == self.foreign_advance_account
        )
        self.assertRecordValues(excess, [{'currency_id': self.other_currency.id, 'amount_currency': -150.0}])

    # -------------------------------------------------------------------------
    # E2. Solo se contabilizan informes aprobados
    # -------------------------------------------------------------------------

    def test_submitted_sheet_cannot_be_posted(self):
        sheet = self.create_sheet([self.receipt_values(100.0)])
        sheet.action_submit_sheet()
        with self.assertRaisesRegex(UserError, 'aprobado'):
            sheet.action_sheet_move_post()
        self.assertFalse(sheet.account_move_ids)

    # -------------------------------------------------------------------------
    # E3 / M4. Pago de la solicitud de anticipo
    # -------------------------------------------------------------------------

    def test_advance_request_payment_goes_to_account_14(self):
        request = self.create_request(self.create_advance_category(), 300.0)
        payment = self.pay_request(request)

        self.assertEqual(payment.partner_id, self.employee_partner)
        self.assertEqual(payment.destination_account_id, self.advance_account)
        advance = payment.move_id.line_ids.filtered(lambda line: line.account_id == self.advance_account)
        self.assertRecordValues(advance, [{'partner_id': self.employee_partner.id, 'balance': 300.0}])

    def test_foreign_currency_advance_request(self):
        foreign_journal = self.env['account.journal'].create({
            'name': 'Banco M.E.', 'code': 'BNKME', 'type': 'bank', 'currency_id': self.other_currency.id,
        })
        category = self.create_advance_category(l10n_pe_payment_journal_ids=[Command.set(foreign_journal.ids)])
        payment = self.pay_request(self.create_request(category, 300.0, currency=self.other_currency))

        self.assertEqual(payment.journal_id, foreign_journal)
        self.assertEqual(payment.currency_id, self.other_currency)
        self.assertEqual(payment.destination_account_id, self.foreign_advance_account)

    def test_foreign_currency_request_requires_a_journal_in_that_currency(self):
        request = self.create_request(self.create_advance_category(), 300.0, currency=self.other_currency)
        with self.assertRaisesRegex(UserError, 'HRK'):
            request._create_and_open_payment()

    def test_regular_payment_category_keeps_the_vendor_flow(self):
        category = self.create_advance_category(l10n_pe_advance_kind=False)
        payment = self.env['account.payment'].browse(
            self.create_request(category, 300.0)._create_and_open_payment()['res_id']
        )
        self.assertNotEqual(payment.destination_account_id, self.advance_account)

    # -------------------------------------------------------------------------
    # E4. La liquidación usa el tipo de cambio de la factura
    # -------------------------------------------------------------------------

    def test_foreign_bill_is_settled_at_its_own_rate(self):
        """El gasto se aprobó a 0.55 (no al 0.50 del día): la 42 se cancela por su
        saldo exacto y la factura no genera diferencia de cambio."""
        self.company.hr_expense_auto_settle = False
        self.create_advance(100.0)
        bill = self.create_receipt_bill(100.0, currency_id=self.other_currency.id, total_amount=55.0)
        self.assertEqual(bill.amount_total_signed, -55.0)

        wizard = self.open_settlement_wizard(bill)
        wizard.line_ids.selected = True
        wizard.action_confirm()

        self.assertEqual(bill.payment_state, 'paid')
        settlement = bill.hr_expense_settlement_move_ids
        self.assertRecordValues(settlement.line_ids.sorted('balance', reverse=True), [
            {'currency_id': self.other_currency.id, 'amount_currency': 100.0, 'balance': 55.0},
            {'currency_id': self.company.currency_id.id, 'amount_currency': -55.0, 'balance': -55.0},
        ])
        payable = bill.line_ids.filtered(lambda line: line.account_id.account_type == 'liability_payable')
        self.assertFalse(payable.matched_debit_ids.exchange_move_id)

    # -------------------------------------------------------------------------
    # M1. Devolución del sobrante en el informe
    # -------------------------------------------------------------------------

    def test_refund_line_creates_a_receipt_reconciled_with_the_advance(self):
        advance = self.create_advance(700.0)
        sheet = self.create_sheet([self.receipt_values(300.0), self.refund_values(400.0)])
        self.assertEqual(sheet.total_amount, 700.0, 'El informe suma lo entregado')

        bills = self.approve_and_post(sheet)

        self.assertEqual(len(bills), 1, 'La devolución no genera factura')
        self.assertTrue(advance.reconciled)
        refund = sheet.expense_line_ids.filtered('l10n_pe_is_advance_refund')
        payment = refund.l10n_pe_refund_payment_id
        self.assertRecordValues(payment, [{
            'payment_type': 'inbound', 'amount': 400.0, 'journal_id': self.bank_journal.id,
            'partner_id': self.employee_partner.id, 'state': 'in_process',
        }])
        self.assertEqual(sheet.state, 'done')
        self.assertFalse(sheet.l10n_pe_balance_to_settle)

    def test_refund_cannot_exceed_the_pending_advance(self):
        self.create_advance(700.0)
        sheet = self.create_sheet([self.receipt_values(300.0), self.refund_values(500.0)])
        with self.assertRaisesRegex(UserError, 'supera'):
            self.approve_and_post(sheet)

    def test_refund_requires_journal(self):
        self.create_advance(700.0)
        sheet = self.create_sheet([self.refund_values(100.0, l10n_pe_refund_journal_id=False)])
        sheet.action_submit_sheet()
        with self.assertRaisesRegex(UserError, 'banco o la caja'):
            sheet.action_approve_expense_sheets()

    def test_refund_in_cash(self):
        advance = self.create_advance(200.0)
        cash_journal = self.company_data['default_journal_cash']
        sheet = self.create_sheet([self.refund_values(200.0, journal=cash_journal)])

        self.approve_and_post(sheet)

        self.assertTrue(advance.reconciled)
        self.assertEqual(sheet.expense_line_ids.l10n_pe_refund_payment_id.journal_id, cash_journal)
        self.assertEqual(sheet.state, 'done', 'Un informe que solo devuelve queda terminado')

    def test_refund_is_paid_by_the_employee_without_receipt(self):
        with self.assertRaises(ValidationError):
            self.env['hr.expense'].create(self.refund_values(100.0, payment_mode='company_account'))
        with self.assertRaises(ValidationError):
            self.env['hr.expense'].create(self.refund_values(100.0, vendor_id=self.vendor.id))
        refund = self.env['hr.expense'].create(self.refund_values(100.0))
        self.assertFalse(refund.tax_ids)
        self.assertFalse(refund._l10n_pe_is_vendor_receipt())

    def test_reset_cancels_the_refund_receipt(self):
        advance = self.create_advance(200.0)
        sheet = self.create_sheet([self.refund_values(200.0)])
        self.approve_and_post(sheet)
        payment = sheet.expense_line_ids.l10n_pe_refund_payment_id

        sheet.action_reset_expense_sheets()

        self.assertEqual(payment.state, 'canceled')
        self.assertFalse(advance.reconciled)
        self.assertFalse(sheet.expense_line_ids.l10n_pe_refund_payment_id)

    # -------------------------------------------------------------------------
    # M2. Saldo por liquidar
    # -------------------------------------------------------------------------

    def test_balance_in_favor_of_the_employee_is_paid_from_the_sheet(self):
        advance = self.create_advance(500.0)
        sheet = self.create_sheet([self.receipt_values(650.0)])
        self.approve_and_post(sheet)
        self.assertTrue(advance.reconciled)
        self.assertEqual(sheet.l10n_pe_balance_to_settle, -150.0)

        payment = self.register_payment(sheet.action_l10n_pe_settle_balance())
        sheet.invalidate_recordset(['l10n_pe_balance_to_settle'])

        self.assertRecordValues(payment, [{'payment_type': 'outbound', 'amount': 150.0, 'partner_id': self.employee_partner.id}])
        self.assertFalse(sheet.l10n_pe_balance_to_settle)

    def test_surplus_not_registered_is_collected_from_the_sheet(self):
        advance = self.create_advance(500.0)
        sheet = self.create_sheet([self.receipt_values(300.0)])
        self.approve_and_post(sheet)
        self.assertEqual(sheet.l10n_pe_balance_to_settle, 200.0)

        payment = self.register_payment(sheet.action_l10n_pe_settle_balance())
        sheet.invalidate_recordset(['l10n_pe_balance_to_settle'])

        self.assertRecordValues(payment, [{'payment_type': 'inbound', 'amount': 200.0}])
        self.assertTrue(advance.reconciled)
        self.assertFalse(sheet.l10n_pe_balance_to_settle)

    def test_no_balance_before_posting(self):
        self.create_advance(500.0)
        sheet = self.create_sheet([self.receipt_values(300.0)])
        self.assertFalse(sheet.l10n_pe_balance_to_settle)
        with self.assertRaisesRegex(UserError, 'saldo'):
            sheet.action_l10n_pe_settle_balance()

    # -------------------------------------------------------------------------
    # M3. Anticipo o fondo elegido en el informe
    # -------------------------------------------------------------------------

    def test_chosen_advance_leaves_older_fund_untouched(self):
        petty_cash = self.create_advance(1000.0, date='2022-01-01')
        advance = self.create_advance(500.0)
        sheet = self.create_sheet([self.receipt_values(300.0)])
        self.assertEqual(sheet.l10n_pe_available_advance_line_ids, petty_cash + advance)
        sheet.l10n_pe_advance_line_id = advance

        self.approve_and_post(sheet)

        self.assertEqual(petty_cash.amount_residual, 1000.0)
        self.assertEqual(advance.amount_residual, 200.0)

    def test_without_choice_the_oldest_advance_is_used(self):
        oldest = self.create_advance(1000.0, date='2022-01-01')
        newest = self.create_advance(500.0)
        self.approve_and_post(self.create_sheet([self.receipt_values(300.0)]))
        self.assertEqual(oldest.amount_residual, 700.0)
        self.assertEqual(newest.amount_residual, 500.0)

    def test_advance_selector_shows_number_date_and_balance(self):
        advance = self.create_advance(500.0)
        name = advance.with_context(l10n_pe_advance_display=True).display_name
        self.assertIn(advance.move_id.name, name)
        self.assertIn(advance.date.strftime('%d/%m/%Y'), name)
        self.assertIn('500.00', name)

    # -------------------------------------------------------------------------
    # M5. Fondo de caja chica
    # -------------------------------------------------------------------------

    def test_petty_cash_fund_with_its_own_configuration(self):
        petty_account = self.env['account.account'].create({
            'code': '141310', 'name': 'Fondo de caja chica', 'account_type': 'asset_receivable', 'reconcile': True,
        })
        petty_settlement_journal = self.env['account.journal'].create({
            'name': 'Liquidación caja chica', 'code': 'LCCH', 'type': 'general',
        })
        petty_payment_journal = self.company_data['default_journal_cash']
        self.company.write({
            'hr_expense_petty_cash_account_id': petty_account.id,
            'hr_expense_petty_cash_settlement_journal_id': petty_settlement_journal.id,
        })
        category = self.create_advance_category('petty_cash', default_payment_journal_id=petty_payment_journal.id,
                                                approver_ids=[Command.create({'user_id': self.env.user.id})])
        fund_payment = self.pay_request(self.create_request(category, 1000.0))
        self.assertEqual(fund_payment.journal_id, petty_payment_journal)
        fund = fund_payment.move_id.line_ids.filtered(lambda line: line.account_id == petty_account)
        self.assertEqual(fund.balance, 1000.0)

        sheet = self.create_sheet([self.receipt_values(420.0)])
        sheet.l10n_pe_advance_line_id = fund
        self.assertTrue(sheet.l10n_pe_is_petty_cash)
        bill = self.approve_and_post(sheet)

        self.assertEqual(bill.hr_expense_settlement_move_ids.journal_id, petty_settlement_journal)
        self.assertEqual(fund.amount_residual, 580.0)
        self.assertFalse(sheet.l10n_pe_balance_to_settle, 'El fondo fijo se repone, no se liquida')

        action = sheet.action_l10n_pe_replenish_fund()
        replenishment = self.env['approval.request'].browse(action['res_id'])
        self.assertRecordValues(replenishment, [{
            'category_id': category.id, 'amount': 420.0, 'l10n_pe_employee_id': self.expense_employee.id,
            'l10n_pe_expense_sheet_id': sheet.id,
        }])
        self.pay_request(replenishment)
        fund_balance = sum(self.env['account.move.line'].search([
            ('account_id', '=', petty_account.id), ('partner_id', '=', self.employee_partner.id),
            ('parent_state', '=', 'posted'),
        ]).mapped('balance'))
        self.assertEqual(fund_balance, 1000.0, 'Al pagar la reposición el fondo vuelve a su monto')

    def test_only_petty_cash_reports_can_be_replenished(self):
        sheet = self.create_sheet([self.receipt_values(100.0)])
        self.approve_and_post(sheet)
        self.assertFalse(sheet.l10n_pe_is_petty_cash)
        with self.assertRaisesRegex(UserError, 'caja chica'):
            sheet.action_l10n_pe_replenish_fund()

    # -------------------------------------------------------------------------
    # M6. Dividir gasto
    # -------------------------------------------------------------------------

    def split(self, expense, amounts, products=None):
        wizard = self.env['hr.expense.split.wizard'].browse(expense.action_split_wizard()['res_id'])
        for index, (line, amount) in enumerate(zip(wizard.expense_split_line_ids, amounts)):
            line.total_amount_currency = amount
            if products and products[index]:
                line.product_id = products[index]
                line._onchange_product_id()
        wizard.action_split_expense()
        return self.env['hr.expense'].search([('l10n_pe_document_reference', '=', expense.l10n_pe_document_reference)])

    def test_split_lines_must_add_up_to_the_receipt_total(self):
        expense = self.env['hr.expense'].create(self.receipt_values(150.0, number='77'))
        lines = self.split(expense, [115.0, 35.0])
        self.assertEqual(lines.mapped('l10n_pe_receipt_total_amount'), [150.0, 150.0])

        lines[1].total_amount_currency = 30.0
        sheet = self._sheet_for(lines)
        with self.assertRaisesRegex(UserError, 'no suman'):
            sheet.action_submit_sheet()

    def test_split_without_document_number_still_gives_one_bill(self):
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        expense = self.env['hr.expense'].create(self.receipt_values(
            150.0, series=False, number=False, l10n_pe_in_purchase_register=False,
        ))
        expense.l10n_pe_document_type_id = False
        self.split(expense, [100.0, 50.0])
        lines = self.env['hr.expense'].search([('vendor_id', '=', self.vendor.id), ('sheet_id', '=', False)])
        self.assertEqual(len(lines), 2)
        bill = self.approve_and_post(self._sheet_for(lines))
        self.assertEqual(len(bill), 1)
        self.assertAlmostEqual(bill.amount_total, 150.0)

    def test_changing_category_in_split_recomputes_igv(self):
        exempt_product = self.env['product.product'].create({
            'name': 'Inafecto', 'can_be_expensed': True, 'supplier_taxes_id': [Command.clear()],
        })
        expense = self.env['hr.expense'].create(self.receipt_values(
            150.0, number='78', tax_ids=[Command.set(self.tax_purchase_a.ids)],
        ))
        lines = self.split(expense, [115.0, 35.0], products=[None, exempt_product])
        exempt_line = lines.filtered(lambda line: line.product_id == exempt_product)
        self.assertFalse(exempt_line.tax_ids, 'La línea toma el IGV de su nueva categoría')

    def _sheet_for(self, expenses):
        return self.env['hr.expense.sheet'].create({
            'name': 'Rendición',
            'employee_id': self.expense_employee.id,
            'company_id': self.company.id,
            'expense_line_ids': [Command.set(expenses.ids)],
        })

    def test_split_keeps_purchase_register_choice(self):
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        expense = self.env['hr.expense'].create(self.receipt_values(
            100.0, number='79', l10n_pe_in_purchase_register=False,
        ))
        lines = self.split(expense, [60.0, 40.0])
        self.assertEqual(lines.mapped('l10n_pe_in_purchase_register'), [False, False])
