from odoo.tests import Form, tagged

from odoo.addons.l10n_pe_hr_expense_settlement.tests.test_expense_rendition_flow import TestExpenseRenditionCommon


@tagged('post_install', '-at_install')
class TestExpenseRatePolicy(TestExpenseRenditionCommon):
    """P7 de la prueba en OMNI del 05/10/2026: cobros y pagos en moneda
    extranjera de la rendición al tipo de cambio compra / venta."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Mismo día, dos tasas como en OMNI: venta 0.50 y compra 0.40 por unidad.
        cls.env['res.currency.rate'].create({
            'name': '2017-01-01',
            'rate': 2.5,
            'currency_id': cls.other_currency.id,
            'company_id': cls.company.id,
            'exchange_rate': 'purchase',
        })

    def liquidity_line(self, payment):
        return payment.move_id.line_ids.filtered(
            lambda line: line.account_id == payment.outstanding_account_id
        )

    def settle_balance(self, sheet):
        action = sheet.action_l10n_pe_settle_balance()
        with Form(self.env[action['res_model']].with_context(**action['context'])) as wizard_form:
            wizard_form.journal_id = self.bank_journal
            wizard_form.payment_date = self.today
        wizard = wizard_form.save()
        return wizard, wizard._create_payments()

    def test_default_policy_is_purchase_for_receipts_and_sale_for_payments(self):
        self.assertEqual(self.company.hr_expense_rate_policy, 'by_direction')
        self.assertEqual(self.company._get_hr_expense_rate_type('inbound'), 'purchase')
        self.assertEqual(self.company._get_hr_expense_rate_type('outbound'), 'sale')

    def test_surplus_is_collected_at_purchase_rate(self):
        """Como PBNK2/2026/00010: el sobrante en moneda extranjera se cobra a TC
        compra (el del banco) y la diferencia queda en la 14 como diferencia de cambio."""
        advance = self.create_foreign_advance(200.0)
        sheet = self.create_sheet([self.receipt_values(50.0, currency_id=self.other_currency.id)])
        self.approve_and_post(sheet)

        wizard, payment = self.settle_balance(sheet)

        self.assertEqual(wizard.exchange_rate_type, 'purchase')
        self.assertRecordValues(payment, [{
            'payment_type': 'inbound', 'amount': 150.0, 'currency_id': self.other_currency.id,
            'exchange_rate_type': 'purchase',
        }])
        self.assertAlmostEqual(self.liquidity_line(payment).balance, 60.0, msg='150 a 0.40')
        self.assertTrue(advance.reconciled)
        sheet.invalidate_recordset(['l10n_pe_balance_to_settle'])
        self.assertFalse(sheet.l10n_pe_balance_to_settle)

    def test_surplus_rate_without_form(self):
        """Mismo caso creando el asistente directamente (RPC), como en staging."""
        self.create_foreign_advance(200.0)
        sheet = self.create_sheet([self.receipt_values(50.0, currency_id=self.other_currency.id)])
        self.approve_and_post(sheet)
        action = sheet.action_l10n_pe_settle_balance()
        wizard = self.env[action['res_model']].with_context(**action['context']).create({
            'journal_id': self.bank_journal.id, 'payment_date': self.today,
        })
        # Como al final de una llamada RPC: los campos calculados se recalculan con
        # un entorno sin el contexto de la acción.
        self.env(context={}).flush_all()
        self.assertEqual(wizard.exchange_rate_type, 'purchase')
        self.assertAlmostEqual(wizard.exchange_rate, 0.4)
        payment = wizard._create_payments()
        self.assertEqual(payment.exchange_rate_type, 'purchase')
        self.assertAlmostEqual(self.liquidity_line(payment).balance, 60.0)

    def test_reimbursement_is_paid_at_sale_rate(self):
        self.create_foreign_advance(200.0)
        sheet = self.create_sheet([self.receipt_values(250.0, currency_id=self.other_currency.id)])
        self.approve_and_post(sheet)

        wizard, payment = self.settle_balance(sheet)

        self.assertEqual(wizard.exchange_rate_type, 'sale')
        self.assertRecordValues(payment, [{'payment_type': 'outbound', 'amount': 50.0, 'exchange_rate_type': 'sale'}])
        self.assertAlmostEqual(self.liquidity_line(payment).balance, -25.0, msg='50 a 0.50')

    def test_company_policy_always_sale(self):
        self.company.hr_expense_rate_policy = 'sale'
        self.create_foreign_advance(200.0)
        sheet = self.create_sheet([self.receipt_values(50.0, currency_id=self.other_currency.id)])
        self.approve_and_post(sheet)

        wizard, payment = self.settle_balance(sheet)
        self.assertEqual(payment.exchange_rate_type, 'sale')
        self.assertAlmostEqual(self.liquidity_line(payment).balance, 75.0)

    def test_company_currency_balance_is_not_affected(self):
        self.create_advance(500.0)
        sheet = self.create_sheet([self.receipt_values(300.0)])
        self.approve_and_post(sheet)
        wizard, payment = self.settle_balance(sheet)
        self.assertFalse(wizard.exchange_rate_type)
        self.assertAlmostEqual(self.liquidity_line(payment).balance, 200.0)

    def test_refund_line_in_foreign_currency_uses_purchase_rate(self):
        advance = self.create_foreign_advance(200.0)
        sheet = self.create_sheet([
            self.receipt_values(150.0, currency_id=self.other_currency.id),
            self.refund_values(50.0, currency_id=self.other_currency.id),
        ])
        self.approve_and_post(sheet)

        refund_payment = sheet.expense_line_ids.l10n_pe_refund_payment_id
        self.assertEqual(refund_payment.exchange_rate_type, 'purchase')
        self.assertAlmostEqual(self.liquidity_line(refund_payment).balance, 20.0, msg='50 a 0.40')
        self.assertTrue(advance.reconciled)

    def test_setting_is_editable_from_expense_settings(self):
        # The chart includes cash-basis taxes: initialize a consistent company
        # before editing the unrelated expense exchange-rate preference.
        self.company.tax_exigibility = True
        with Form(self.env['res.config.settings'].with_company(self.company)) as settings:
            settings.hr_expense_rate_policy = 'purchase'
        self.assertEqual(self.company.hr_expense_rate_policy, 'purchase')
