from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_pe_hr_expense_settlement.tests.common import TestExpenseSettlementCommon


@tagged('post_install', '-at_install')
class TestExpenseIntercompany(TestExpenseSettlementCommon):
    """P13 (13/10/2026): rendir en OMNI comprobantes emitidos a otra empresa del grupo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.write({'vat': '20604225613', 'hr_expense_auto_settle': True})
        cls.receivable_ic = cls.env['account.account'].create({
            'code': '169900', 'name': 'Otras cuentas por cobrar diversas', 'account_type': 'asset_receivable',
            'reconcile': True,
        })
        cls.company.hr_expense_ic_receivable_account_id = cls.receivable_ic

        cls.dest_data = cls.setup_other_company(name='JE-AL (test)')
        cls.dest = cls.dest_data['company']
        cls.payable_ic = cls.env['account.account'].with_company(cls.dest).create({
            'code': '469900', 'name': 'Otras cuentas por pagar diversas', 'account_type': 'liability_payable',
            'reconcile': True,
        })
        cls.dest.write({
            'vat': '20552711867',
            'hr_expense_ic_receive': True,
            'hr_expense_ic_payable_account_id': cls.payable_ic.id,
            'hr_expense_settlement_journal_id': cls.dest_data['default_journal_misc'].id,
        })
        cls.tax_origin = cls.env['account.tax'].create({
            'name': '18%-C', 'amount': 18.0, 'type_tax_use': 'purchase', 'company_id': cls.company.id,
        })
        cls.tax_dest = cls.env['account.tax'].with_company(cls.dest).create({
            'name': '18%-C', 'amount': 18.0, 'type_tax_use': 'purchase', 'company_id': cls.dest.id,
        })

    def ic_values(self, amount, number='80', **values):
        return self.receipt_values(amount, number=number, **{
            'l10n_pe_charged_partner_id': self.dest.partner_id.id,
            'l10n_pe_ic_customer_vat': '20552711867',
            **values,
        })

    def dest_bill(self, expense):
        return self.env['account.move'].browse(expense.l10n_pe_ic_bill_res_id)

    def test_receipt_of_another_company(self):
        """Fondo de 500: comprobante de OMNI por 120 y de JE-AL por 80."""
        advance = self.create_advance(500.0)
        sheet = self.create_sheet([self.receipt_values(120.0, number='120'), self.ic_values(80.0)])
        own, ic = sheet.expense_line_ids
        self.assertFalse(own.l10n_pe_is_intercompany)
        self.assertEqual(own.l10n_pe_charged_partner_id, self.company.partner_id, 'Por defecto, la empresa del informe')
        self.assertTrue(ic.l10n_pe_is_intercompany)
        self.assertIn(self.dest.partner_id, ic.l10n_pe_ic_allowed_partner_ids)

        bills = self.approve_and_post(sheet)

        # En OMNI: factura solo del comprobante propio; el de JE-AL va a la cuenta por cobrar.
        self.assertEqual(len(bills), 1)
        self.assertEqual(bills.amount_total, 120.0)
        move = ic.l10n_pe_ic_move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.ref, sheet.name)
        self.assertRecordValues(move.line_ids.sorted('balance'), [
            {'account_id': self.advance_account.id, 'partner_id': self.employee_partner.id, 'balance': -80.0,
             'reconciled': True},
            {'account_id': self.receivable_ic.id, 'partner_id': self.dest.partner_id.id, 'balance': 80.0,
             'reconciled': False},
        ])
        self.assertEqual(advance.amount_residual, 300.0, 'El fondo baja en 200 (120 + 80)')

        # En JE-AL: factura en borrador con los datos del comprobante.
        bill = self.dest_bill(ic)
        self.assertRecordValues(bill, [{
            'company_id': self.dest.id, 'move_type': 'in_invoice', 'state': 'draft', 'partner_id': self.vendor.id,
            'ref': ic.l10n_pe_document_reference, 'amount_total': 80.0, 'l10n_pe_ic_origin_partner_id': self.company.partner_id.id,
            'l10n_pe_ic_origin_ref': sheet.name,
        }])
        self.assertIn(sheet.name, bill.message_ids[0].body)
        self.assertNotIn(self.dest, self.expense_user_employee.company_ids, 'El empleado no tiene acceso a JE-AL')
        self.assertIn(bill, self.env['account.move'].search([('l10n_pe_ic_origin_partner_id', '!=', False)]),
                      'Lista "Gastos recibidos de otras empresas"')

        # La contadora de JE-AL publica: reconoce la deuda con OMNI.
        bill.action_post()
        payable_move = bill.l10n_pe_ic_payable_move_id
        self.assertEqual(payable_move.ref, sheet.name, 'Misma referencia en las dos empresas')
        self.assertEqual(bill.payment_state, 'paid')
        ic_line = payable_move.line_ids.filtered(lambda line: line.account_id == self.payable_ic)
        self.assertRecordValues(ic_line, [{'partner_id': self.company.partner_id.id, 'balance': -80.0}])

        with self.assertRaisesRegex(UserError, 'ya se publicaron'):
            sheet.action_reset_expense_sheets()

        # Si la contadora la vuelve a borrador, se anula el reconocimiento.
        bill.button_draft()
        self.assertEqual(payable_move.state, 'cancel')
        self.assertFalse(bill.l10n_pe_ic_payable_move_id)

    def test_only_intercompany_receipts(self):
        advance = self.create_advance(80.0)
        sheet = self.create_sheet([self.ic_values(80.0)])
        self.approve_and_post(sheet)
        self.assertFalse(sheet.account_move_ids, 'Sin factura en OMNI')
        self.assertEqual(sheet.state, 'done')
        self.assertTrue(advance.reconciled)
        self.assertEqual(sheet.l10n_pe_ic_move_count, 1)

    def test_reset_cancels_both_sides(self):
        advance = self.create_advance(500.0)
        sheet = self.create_sheet([self.ic_values(80.0)])
        self.approve_and_post(sheet)
        ic = sheet.expense_line_ids
        move, bill = ic.l10n_pe_ic_move_id, self.dest_bill(ic)

        sheet.action_reset_expense_sheets()

        self.assertEqual(sheet.state, 'draft')
        self.assertEqual(move.state, 'cancel')
        self.assertEqual(bill.state, 'cancel')
        self.assertEqual(advance.amount_residual, 500.0)
        self.assertFalse(ic.l10n_pe_ic_move_id or ic.l10n_pe_ic_bill_res_id)
        # Se puede volver a rendir (la factura anulada no cuenta como duplicada).
        self.approve_and_post(sheet)
        self.assertEqual(self.dest_bill(ic).state, 'draft')

    def test_taxes_are_mapped_by_name(self):
        self.create_advance(500.0)
        sheet = self.create_sheet([self.ic_values(118.0, tax_ids=[Command.set(self.tax_origin.ids)])])
        self.approve_and_post(sheet)
        bill = self.dest_bill(sheet.expense_line_ids)
        self.assertEqual(bill.invoice_line_ids.tax_ids, self.tax_dest)
        self.assertRecordValues(bill, [{'amount_untaxed': 100.0, 'amount_tax': 18.0, 'amount_total': 118.0}])

    def test_checks_before_sending(self):
        sheet = self.create_sheet([self.ic_values(80.0, l10n_pe_ic_customer_vat=False)])
        with self.assertRaisesRegex(UserError, 'indique el RUC del adquiriente'):
            sheet.action_submit_sheet()

        sheet.expense_line_ids.l10n_pe_ic_customer_vat = '20552711867'
        self.dest.hr_expense_ic_receive = False
        with self.assertRaisesRegex(UserError, 'no recibe gastos de otras empresas'):
            sheet.action_submit_sheet()
        self.assertNotIn(self.dest.partner_id, sheet.expense_line_ids.l10n_pe_ic_allowed_partner_ids)

    def test_customer_vat_follows_the_charged_company(self):
        """Nota 20/10 punto 1: el RUC se completa con el de la empresa elegida y se
        actualiza al cambiarla; si se cambia a mano se advierte, sin bloquear."""
        values = self.ic_values(80.0)
        del values['l10n_pe_ic_customer_vat']
        sheet = self.create_sheet([values])
        expense = sheet.expense_line_ids
        self.assertEqual(expense.l10n_pe_ic_customer_vat, '20552711867')
        self.assertFalse(sheet.l10n_pe_ic_vat_warning)

        expense.l10n_pe_charged_partner_id = self.company.partner_id
        self.assertFalse(expense.l10n_pe_ic_customer_vat, 'Gasto propio: sin RUC del adquiriente')
        expense.l10n_pe_charged_partner_id = self.dest.partner_id
        self.assertEqual(expense.l10n_pe_ic_customer_vat, '20552711867')

        expense.l10n_pe_ic_customer_vat = '20611680067'
        self.assertTrue(expense.l10n_pe_ic_vat_mismatch)
        self.assertIn('20611680067', sheet.l10n_pe_ic_vat_warning)
        self.assertIn('warning', expense._onchange_l10n_pe_ic_customer_vat())
        self.create_advance(500.0)
        self.approve_and_post(sheet)
        self.assertEqual(self.dest_bill(expense).state, 'draft', 'El RUC distinto no bloquea')

    def test_default_account_of_the_other_company(self):
        """Sin cuenta configurada se usa la 4699000 de la otra empresa, aunque la compañía activa sea OMNI
        (el código de la cuenta depende de la compañía)."""
        account = self.env['account.account'].with_company(self.dest).create({
            'code': '4699000', 'name': 'Otras cuentas por pagar M.N.', 'account_type': 'liability_payable',
            'reconcile': True,
        })
        self.dest.hr_expense_ic_payable_account_id = False
        self.assertEqual(self.env.company, self.company)
        self.assertEqual(self.dest._get_hr_expense_ic_account('payable', self.dest.currency_id), account)

    def test_closed_period_in_the_other_company(self):
        self.create_advance(500.0)
        sheet = self.create_sheet([self.ic_values(80.0)])
        sheet.accounting_date = self.today
        self.dest.fiscalyear_lock_date = self.today
        self.approve_and_post(sheet)
        bill = self.dest_bill(sheet.expense_line_ids)
        self.assertGreater(bill.date, self.today)
        self.assertIn('está cerrado', bill.message_ids[0].body)

    def test_receipt_already_registered_in_the_other_company(self):
        existing = self.env['account.move'].with_company(self.dest).create({
            'move_type': 'in_invoice', 'company_id': self.dest.id, 'partner_id': self.vendor.id, 'ref': 'F001-00000080',
            'invoice_date': self.today, 'l10n_latam_document_type_id': self.document_type_invoice.id,
            'invoice_line_ids': [Command.create({'name': 'Gasto', 'quantity': 1, 'price_unit': 80.0, 'tax_ids': []})],
        })
        existing.l10n_latam_document_type_id = self.document_type_invoice
        sheet = self.create_sheet([self.ic_values(80.0)])
        with self.assertRaisesRegex(UserError, 'ya fueron rendidos o registrados'):
            sheet.action_submit_sheet()
        existing.button_cancel()
        sheet.action_submit_sheet()

    def create_origin_category(self, name, code=False):
        return self.env['product.product'].create({
            'name': name, 'default_code': code or ('TEST-ORIGIN-' + name), 'can_be_expensed': True, 'company_id': self.company.id,
            'standard_price': 0.0,
        })

    def create_dest_product(self, name, code=False, account_code='631120'):
        account = self.env['account.account'].with_company(self.dest).create({
            'code': account_code, 'name': name, 'account_type': 'expense',
        })
        return self.env['product.product'].with_company(self.dest).create({
            'name': name, 'default_code': code or ('TEST-DEST-' + name), 'company_id': self.dest.id, 'purchase_ok': True,
            'property_account_expense_id': account.id, 'supplier_taxes_id': [Command.set(self.tax_dest.ids)],
        })

    def bill_line(self, category, amount=118.0):
        self.create_advance(500.0)
        sheet = self.create_sheet([self.ic_values(amount, number=str(category.id), product_id=category.id,
                                                  tax_ids=[Command.set(self.tax_origin.ids)])])
        self.approve_and_post(sheet)
        bill = self.dest_bill(sheet.expense_line_ids)
        return bill, bill.invoice_line_ids

    def test_bill_line_product(self):
        """Nota 20/10 punto 2: la línea de la factura de la otra empresa lleva producto
        y de él toma la cuenta y los impuestos."""
        # Producto compartido: el mismo.
        self.product_c.can_be_expensed = True
        bill, line = self.bill_line(self.product_c)
        self.assertEqual(line.product_id, self.product_c)

        # Producto de OMNI: el de JE-AL con el mismo código.
        same_code = self.create_dest_product('Movilidad JE-AL', code='MOV', account_code='631120')
        bill, line = self.bill_line(self.create_origin_category('Movilidad', code='MOV'))
        self.assertRecordValues(line, [{'product_id': same_code.id, 'account_id': same_code.property_account_expense_id.id,
                                        'tax_ids': self.tax_dest.ids}])
        self.assertEqual(bill.amount_total, 118.0)

    def test_bill_line_product_by_equivalence_or_default(self):
        category = self.create_origin_category('Transporte')
        transport = self.create_dest_product('Servicio de Transporte', account_code='631110')
        self.env['hr.expense.ic.product'].create({
            'company_id': self.dest.id, 'origin_product_id': category.id, 'product_id': transport.id,
        })
        bill, line = self.bill_line(category)
        self.assertRecordValues(line, [{'product_id': transport.id,
                                        'account_id': transport.property_account_expense_id.id}])

        default = self.create_dest_product('Otros gastos', account_code='659900')
        self.dest.hr_expense_ic_default_product_id = default
        bill, line = self.bill_line(self.create_origin_category('Sin equivalencia'))
        self.assertEqual(line.product_id, default)
        self.assertIn('producto por defecto', bill.message_ids[0].body)
