from odoo import Command
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tests import Form, tagged

from .common import TestExpenseSettlementCommon


@tagged('post_install', '-at_install')
class TestExpenseReceiptBills(TestExpenseSettlementCommon):

    def test_document_reference_is_normalized(self):
        expense = self.env['hr.expense'].create(self.receipt_values(100.0, series=' f001 ', number='123'))
        self.assertEqual(expense.l10n_pe_document_reference, 'F001-00000123')

        expense.l10n_pe_document_number = 'ABC123'
        self.assertEqual(expense.l10n_pe_document_reference, 'F001-ABC123', 'Non numeric numbers are kept as typed.')

        expense.l10n_pe_document_series = False
        self.assertFalse(expense.l10n_pe_document_reference)

    def test_document_onchange_normalizes_inputs(self):
        with Form(self.env['hr.expense'].with_context(default_employee_id=self.expense_employee.id)) as expense_form:
            expense_form.product_id = self.product_c
            expense_form.total_amount_currency = 10.0
            expense_form.vendor_id = self.vendor
            expense_form.l10n_pe_document_type_id = self.document_type_invoice
            expense_form.l10n_pe_document_series = 'e001'
            expense_form.l10n_pe_document_number = '45'
            self.assertEqual(expense_form.l10n_pe_document_series, 'E001')
            self.assertEqual(expense_form.l10n_pe_document_number, '00000045')

    def test_document_parts_cannot_contain_separators(self):
        with self.assertRaises(ValidationError):
            self.env['hr.expense'].create(self.receipt_values(100.0, series='F-01'))
        with self.assertRaises(ValidationError):
            self.env['hr.expense'].create(self.receipt_values(100.0, number='12 34'))

    def test_one_vendor_bill_per_receipt(self):
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        sheet = self.create_sheet([
            # Dos líneas de un mismo comprobante (p.ej. "Dividir gasto").
            self.receipt_values(300.0, number='10', name='Almuerzo'),
            self.receipt_values(200.0, number='0010', name='Cena'),
            self.receipt_values(150.0, vendor=self.vendor_2, series='B002', number='7'),
            # Gasto sin comprobante de proveedor: factura a nombre del empleado.
            {**self.no_receipt_values(50.0), 'name': 'Movilidad'},
        ])
        moves = self.approve_and_post(sheet)

        self.assertEqual(len(moves), 3)
        self.assertTrue(all(move.move_type == 'in_invoice' and move.state == 'posted' for move in moves))
        self.assertRecordValues(moves.sorted('amount_total'), [
            {'partner_id': self.employee_partner.id, 'amount_total': 50.0, 'ref': sheet.name},
            {'partner_id': self.vendor_2.id, 'amount_total': 150.0, 'ref': 'B002-00000007'},
            {'partner_id': self.vendor.id, 'amount_total': 500.0, 'ref': 'F001-00000010'},
        ])
        vendor_bill = moves.filtered(lambda move: move.partner_id == self.vendor)
        self.assertRecordValues(vendor_bill, [{
            'l10n_latam_document_type_id': self.document_type_invoice.id,
            'invoice_date': self.today,
            'expense_sheet_id': sheet.id,
            'journal_id': sheet.journal_id.id,
        }])
        self.assertEqual(len(vendor_bill.invoice_line_ids), 2)
        self.assertEqual(vendor_bill.invoice_line_ids.partner_id, self.vendor)
        self.assertEqual(
            vendor_bill.line_ids.filtered(lambda line: line.account_id.account_type == 'liability_payable').partner_id,
            self.vendor,
        )
        self.assertEqual(sheet.state, 'post')
        self.assertEqual(sheet.amount_residual, 700.0)

    def test_expenses_without_receipt_go_out_of_the_register(self):
        """P1 (OMNI 05/10): movilidad sin sustento -> diario fuera del Registro de
        Compras, a nombre del empleado y sin tipo de documento."""
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        sheet = self.create_sheet([self.no_receipt_values(100.0), self.no_receipt_values(40.0)])
        move = self.approve_and_post(sheet)

        self.assertEqual(len(move), 1)
        self.assertRecordValues(move, [{
            'partner_id': self.employee_partner.id,
            'amount_total': 140.0,
            'ref': sheet.name,
            'journal_id': self.non_register_journal.id,
            'l10n_latam_document_type_id': False,
            'state': 'posted',
        }])

    def test_expense_without_receipt_requires_out_of_register_journal(self):
        sheet = self.create_sheet([self.no_receipt_values(40.0)])
        sheet.action_submit_sheet()
        with self.assertRaises(RedirectWarning):
            sheet.action_approve_expense_sheets()

    def test_register_requires_vendor_and_document_data_on_submit(self):
        """P2 (OMNI 05/10): con "Va al Registro de Compras" no se puede enviar el
        informe sin proveedor, tipo de documento, serie y número."""
        sheet = self.create_sheet([
            {**self.no_receipt_values(40.0, name='Sin proveedor'), 'l10n_pe_in_purchase_register': True},
            self.receipt_values(50.0, name='Sin tipo', l10n_pe_document_type_id=False),
        ])
        with self.assertRaisesRegex(UserError, r'(?s)Sin proveedor: proveedor, tipo de documento, serie, número.*Sin tipo: tipo de documento'):
            sheet.action_submit_sheet()
        self.assertEqual(sheet.state, 'draft')

        sheet.expense_line_ids.l10n_pe_in_purchase_register = False
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        sheet.action_submit_sheet()
        self.assertEqual(sheet.state, 'submit')

    def test_register_fields_are_required_in_the_form(self):
        with Form(self.env['hr.expense'].with_context(default_employee_id=self.expense_employee.id)) as expense_form:
            expense_form.product_id = self.product_c
            expense_form.total_amount_currency = 40.0
            self.assertTrue(expense_form.l10n_pe_in_purchase_register)
            for field in ('vendor_id', 'l10n_pe_document_type_id', 'l10n_pe_document_series', 'l10n_pe_document_number'):
                self.assertTrue(expense_form._get_modifier(field, 'required'), field)
            expense_form.l10n_pe_in_purchase_register = False
            for field in ('vendor_id', 'l10n_pe_document_type_id', 'l10n_pe_document_series', 'l10n_pe_document_number'):
                self.assertFalse(expense_form._get_modifier(field, 'required'), field)
        self.assertFalse(expense_form.record.vendor_id)

    def test_taxes_are_price_included_like_native_expenses(self):
        bill = self.create_receipt_bill(118.0, tax_ids=[Command.set(self.tax_purchase_a.ids)])
        self.assertAlmostEqual(bill.amount_total, 118.0)
        self.assertAlmostEqual(bill.amount_tax, 118.0 - 118.0 / 1.15, places=2)

    def test_receipt_in_foreign_currency_keeps_its_currency(self):
        foreign = self.other_currency
        bill = self.create_receipt_bill(100.0, currency_id=foreign.id)
        expense = bill.line_ids.expense_id

        self.assertEqual(bill.currency_id, foreign)
        self.assertAlmostEqual(bill.amount_total, 100.0)
        # Mismo tipo de cambio aprobado en el gasto.
        self.assertAlmostEqual(-bill.amount_total_signed, expense.total_amount)
        self.assertEqual(expense.total_amount, 50.0)

    def test_receipt_out_of_purchase_register_uses_configured_journal(self):
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        bill = self.create_receipt_bill(80.0, l10n_pe_in_purchase_register=False, l10n_pe_document_type_id=False)
        self.assertEqual(bill.journal_id, self.non_register_journal)
        self.assertEqual(bill.partner_id, self.vendor)

    def test_receipt_out_of_purchase_register_requires_journal(self):
        sheet = self.create_sheet([self.receipt_values(80.0, l10n_pe_in_purchase_register=False)])
        sheet.action_submit_sheet()
        with self.assertRaises(RedirectWarning):
            sheet.action_approve_expense_sheets()

    def test_purchase_register_receipt_requires_document_data(self):
        sheet = self.create_sheet([self.receipt_values(80.0, l10n_pe_document_type_id=False)])
        with self.assertRaisesRegex(UserError, 'Comprobante F001-123: tipo de documento'):
            sheet.action_submit_sheet()
        # También si se llega a aprobar por otra vía (p.ej. datos importados).
        sheet.approval_state = 'submit'
        with self.assertRaisesRegex(UserError, 'Comprobante F001-123: tipo de documento'):
            sheet.action_approve_expense_sheets()
        self.assertFalse(sheet.account_move_ids)

    def test_sheet_payment_state_with_several_bills(self):
        sheet = self.create_sheet([
            self.receipt_values(300.0, number='1'),
            self.receipt_values(200.0, number='2'),
        ])
        bill_1, bill_2 = self.approve_and_post(sheet).sorted('amount_total', reverse=True)
        self.assertEqual(sheet.payment_state, 'not_paid')

        self.env['account.payment.register'].with_context(active_model='account.move', active_ids=bill_1.ids).create({
            'payment_date': self.today,
        })._create_payments()
        self.assertEqual(sheet.payment_state, 'partial')
        self.assertEqual(sheet.state, 'done')
        self.assertEqual(sheet.amount_residual, 200.0)

        self.env['account.payment.register'].with_context(active_model='account.move', active_ids=bill_2.ids).create({
            'payment_date': self.today,
        })._create_payments()
        self.assertIn(sheet.payment_state, ('paid', 'in_payment'))
        self.assertEqual(sheet.amount_residual, 0.0)

    def test_reset_sheet_cancels_every_receipt_bill(self):
        """P14 (13/10/2026): con el periodo abierto las facturas se anulan (no se crea una
        nota de crédito que el proveedor no emitió)."""
        sheet = self.create_sheet([
            self.receipt_values(300.0, number='1'),
            self.receipt_values(200.0, number='2'),
        ])
        bills = self.approve_and_post(sheet)
        sheet.action_reset_expense_sheets()

        self.assertEqual(sheet.state, 'draft')
        self.assertFalse(sheet.account_move_ids)
        self.assertEqual(set(bills.mapped('state')), {'cancel'})
        self.assertFalse(bills.reversal_move_ids)

    def test_employee_cost_center_flows_to_expenses(self):
        distribution = {str(self.analytic_account_1.id): 100}
        self.expense_employee.expense_analytic_distribution = distribution

        expense = self.env['hr.expense'].create(self.receipt_values(100.0))
        self.assertEqual(expense.analytic_distribution, distribution)

        bill = self.create_receipt_bill(100.0)
        self.assertEqual(bill.invoice_line_ids.analytic_distribution, distribution)

    def test_expense_without_employee_cost_center_keeps_native_distribution(self):
        expense = self.env['hr.expense'].create(self.receipt_values(
            100.0, analytic_distribution={str(self.analytic_account_2.id): 100},
        ))
        self.assertEqual(expense.analytic_distribution, {str(self.analytic_account_2.id): 100})

    def test_issue_date_differs_from_accounting_date(self):
        sheet = self.create_sheet([self.receipt_values(100.0, date='2022-01-10')])
        sheet.accounting_date = '2022-01-25'
        bill = self.approve_and_post(sheet)
        self.assertRecordValues(bill, [{'invoice_date': self.today.replace(day=10), 'date': self.today}])

    def test_sheet_with_receipts_is_settled_from_the_bills(self):
        receipt_sheet = self.create_sheet([self.receipt_values(100.0)])
        employee_sheet = self.create_sheet([{**self.receipt_values(100.0), 'vendor_id': False}])
        self.assertTrue(receipt_sheet.l10n_pe_has_vendor_receipts)
        self.assertFalse(employee_sheet.l10n_pe_has_vendor_receipts)

        company_paid_sheet = self.create_sheet([{**self.receipt_values(100.0), 'payment_mode': 'company_account'}])
        self.assertFalse(company_paid_sheet.l10n_pe_has_vendor_receipts)

    def test_company_paid_expenses_keep_native_flow(self):
        sheet = self.create_sheet([{**self.receipt_values(100.0), 'payment_mode': 'company_account'}])
        move = self.approve_and_post(sheet)
        self.assertEqual(move.move_type, 'entry')
        self.assertTrue(move.origin_payment_id)
        self.assertFalse(move.hr_expense_can_settle)

    # -------------------------------------------------------------------------
    # Solo los datos del comprobante que pide la localización
    # -------------------------------------------------------------------------

    def test_receipt_has_no_fields_outside_the_localization(self):
        """Como una factura de proveedor normal: sin asignación de IGV, clasificación,
        rubro ECPN ni comerciante (el comerciante es el proveedor)."""
        removed = {'l10n_pe_igv_assignment_id', 'l10n_pe_ecpn_category_id', 'l10n_pe_merchant_id', 'types_goods_services_id'}
        self.assertFalse(removed & set(self.env['hr.expense']._fields))
        self.assertNotIn('l10n_pe_in_purchase_register', self.env['account.move']._fields)

    def test_purchase_register_is_chosen_in_the_expense(self):
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        expense = self.env['hr.expense'].create(self.receipt_values(100.0))
        self.assertTrue(expense.l10n_pe_in_purchase_register, 'Por defecto va al Registro de Compras')
        bill = self.create_receipt_bill(100.0, number='2', l10n_pe_in_purchase_register=False)
        self.assertEqual(bill.journal_id, self.non_register_journal)

    # -------------------------------------------------------------------------
    # Un comprobante no se rinde dos veces
    # -------------------------------------------------------------------------

    def test_receipt_cannot_be_rendered_twice(self):
        self.create_receipt_bill(100.0, number='55')
        # Otro monto: el control nativo de gastos duplicados no se adelanta al nuestro.
        sheet = self.create_sheet([self.receipt_values(150.0, number='55', name='Mismo comprobante')])
        with self.assertRaisesRegex(UserError, 'ya fueron rendidos o registrados'):
            sheet.action_submit_sheet()

    def test_receipt_already_registered_as_vendor_bill(self):
        existing = self.init_invoice('in_invoice', partner=self.vendor, amounts=[100.0], post=True)
        existing.write({'ref': 'F001-00000077', 'l10n_latam_document_type_id': self.document_type_invoice.id})
        sheet = self.create_sheet([self.receipt_values(100.0, number='77')])
        with self.assertRaisesRegex(UserError, 'ya fueron rendidos o registrados'):
            sheet.action_submit_sheet()

    def test_same_receipt_lines_in_one_sheet_and_after_reset(self):
        sheet = self.create_sheet([
            self.receipt_values(60.0, number='9', name='Línea gravada'),
            self.receipt_values(40.0, number='9', name='Línea inafecta'),
        ])
        bill = self.approve_and_post(sheet)
        self.assertEqual(len(bill.invoice_line_ids), 2)

        # Al restablecer el informe la factura se revierte y se puede volver a aprobar.
        sheet.action_reset_expense_sheets()
        sheet.action_submit_sheet()
        sheet.action_approve_expense_sheets()
        self.assertTrue(sheet.account_move_ids)

    def test_native_split_gives_one_bill_with_several_lines(self):
        """Comprobante con un ítem gravado (118 con IGV) y otro inafecto (32)."""
        expense = self.env['hr.expense'].create(self.receipt_values(
            150.0, number='55', tax_ids=[Command.set(self.tax_purchase_a.ids)],
        ))
        wizard = self.env['hr.expense.split.wizard'].browse(expense.action_split_wizard()['res_id'])
        taxed, exempt = wizard.expense_split_line_ids
        taxed.total_amount_currency = 115.0
        exempt.write({'total_amount_currency': 35.0, 'tax_ids': [Command.clear()]})
        wizard.action_split_expense()

        lines = self.env['hr.expense'].search([('l10n_pe_document_reference', '=', 'F001-00000055')])
        self.assertEqual(len(lines), 2)
        self.assertEqual(set(lines.mapped('vendor_id')), {self.vendor})
        bill = self.approve_and_post(self._sheet_for(lines))
        self.assertEqual(len(bill), 1)
        self.assertEqual(len(bill.invoice_line_ids), 2)
        self.assertAlmostEqual(bill.amount_total, 150.0)
        self.assertAlmostEqual(bill.amount_tax, 115.0 - 115.0 / 1.15, places=2)

    def _sheet_for(self, expenses):
        return self.env['hr.expense.sheet'].create({
            'name': 'Rendición',
            'employee_id': self.expense_employee.id,
            'company_id': self.company.id,
            'expense_line_ids': [Command.set(expenses.ids)],
        })
