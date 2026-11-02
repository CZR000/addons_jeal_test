from odoo import Command
from odoo.tests import Form, tagged

from .test_expense_rendition_flow import TestExpenseRenditionCommon


@tagged('post_install', '-at_install')
class TestExpenseOmniObservations(TestExpenseRenditionCommon):
    """Observaciones de la prueba en OMNI del 05/10/2026 (P5, P6, P8)."""

    # -------------------------------------------------------------------------
    # P5. La lista "Anticipo / fondo" solo ofrece la moneda de los comprobantes
    # -------------------------------------------------------------------------

    def test_advance_list_only_offers_the_receipts_currency(self):
        local_advance = self.create_advance(500.0)
        foreign_advance = self.create_foreign_advance(200.0)

        empty_sheet = self.create_sheet([])
        self.assertEqual(empty_sheet.l10n_pe_available_advance_line_ids, local_advance + foreign_advance,
                         'Sin comprobantes aún se ofrecen todos')

        local_sheet = self.create_sheet([self.receipt_values(100.0)])
        self.assertEqual(local_sheet.l10n_pe_available_advance_line_ids, local_advance)

        foreign_sheet = self.create_sheet([self.receipt_values(100.0, currency_id=self.other_currency.id)])
        self.assertEqual(foreign_sheet.l10n_pe_available_advance_line_ids, foreign_advance)

    def test_advance_of_another_currency_shows_a_warning(self):
        self.create_advance(500.0)
        foreign_advance = self.create_foreign_advance(200.0)
        sheet = self.create_sheet([self.receipt_values(100.0)])
        self.assertFalse(sheet.l10n_pe_advance_currency_warning)

        sheet.l10n_pe_advance_line_id = foreign_advance
        self.assertIn(self.other_currency.name, sheet.l10n_pe_advance_currency_warning)
        self.assertIn(self.company.currency_id.name, sheet.l10n_pe_advance_currency_warning)

    def test_advance_list_follows_the_lines_in_the_form(self):
        local_advance = self.create_advance(500.0)
        foreign_advance = self.create_foreign_advance(200.0)
        expense = self.env['hr.expense'].create(self.receipt_values(100.0, currency_id=self.other_currency.id))
        # Registro en edición (como en el formulario, antes de guardar).
        sheet = self.env['hr.expense.sheet'].new({
            'name': 'Rendición', 'employee_id': self.expense_employee.id, 'company_id': self.company.id,
        })
        self.assertEqual(sheet.l10n_pe_available_advance_line_ids._origin, local_advance + foreign_advance)
        sheet.expense_line_ids = [Command.link(expense.id)]
        self.assertEqual(sheet.l10n_pe_available_advance_line_ids._origin, foreign_advance)

    # -------------------------------------------------------------------------
    # P6. El pago de la entrega usa el método de salida del diario
    # -------------------------------------------------------------------------

    def test_advance_payment_uses_an_outbound_method(self):
        """En OMNI la categoría tenía por defecto el "Manual" de entrada del banco
        (Recibos pendientes): el pago de la entrega salía por la cuenta de cobros."""
        inbound_account = self.env['account.account'].create({
            'code': '104102', 'name': 'Recibos pendientes', 'account_type': 'asset_current', 'reconcile': True,
        })
        outbound_account = self.env['account.account'].create({
            'code': '104103', 'name': 'Pagos pendientes', 'account_type': 'asset_current', 'reconcile': True,
        })
        inbound_method = self.bank_journal.inbound_payment_method_line_ids[:1]
        outbound_method = self.bank_journal.outbound_payment_method_line_ids[:1]
        inbound_method.payment_account_id = inbound_account
        outbound_method.payment_account_id = outbound_account
        category = self.create_advance_category(default_payment_method_line_id=inbound_method.id)

        payment = self.pay_request(self.create_request(category, 500.0))

        self.assertEqual(payment.payment_method_line_id, outbound_method)
        self.assertEqual(payment.outstanding_account_id, outbound_account)
        self.assertEqual(
            payment.move_id.line_ids.filtered(lambda line: line.credit).account_id, outbound_account,
        )

    def test_advance_category_only_offers_outbound_methods(self):
        domain = self.env['approval.category']._fields['default_payment_method_line_id'].domain
        self.assertIn("('payment_type', '=', 'outbound')", domain)
        inbound_method = self.bank_journal.inbound_payment_method_line_ids[:1]
        with Form(self.create_advance_category(default_payment_method_line_id=inbound_method.id)) as category_form:
            category_form.default_payment_journal_id = self.company_data['default_journal_cash']
            self.assertFalse(category_form.default_payment_method_line_id, 'Otro diario: se limpia el método')

    # -------------------------------------------------------------------------
    # P8. Aviso cuando una línea de gasto parece una devolución
    # -------------------------------------------------------------------------

    def test_expense_described_as_refund_is_flagged(self):
        expense = self.env['hr.expense'].create(self.receipt_values(200.0, name='Devolución de entrega a rendir'))
        self.assertTrue(expense.l10n_pe_looks_like_refund)

        for name in ('Sobrante del viaje', 'Reintegro de saldo', 'Le DEVUELVO lo que sobró'):
            expense.name = name
            self.assertTrue(expense.l10n_pe_looks_like_refund, name)

        expense.name = 'Almuerzo con cliente'
        self.assertFalse(expense.l10n_pe_looks_like_refund)
        expense.description = 'devolución del sobrante'
        self.assertTrue(expense.l10n_pe_looks_like_refund, 'También en las notas')

        refund = self.env['hr.expense'].create(self.refund_values(200.0, name='Devolución de entrega a rendir'))
        self.assertFalse(refund.l10n_pe_looks_like_refund, 'Con la categoría correcta no hay aviso')

    def test_sheet_warns_about_refund_like_lines(self):
        sheet = self.create_sheet([self.receipt_values(300.0, name='Pasaje')])
        self.assertFalse(sheet.l10n_pe_has_refund_hints)
        sheet.expense_line_ids = [Command.create(self.receipt_values(
            200.0, number='2', name='Devolución de entrega a rendir',
        ))]
        self.assertTrue(sheet.l10n_pe_has_refund_hints)
