from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_pe_hr_expense_settlement.tests.common import TestExpenseSettlementCommon


@tagged('post_install', '-at_install')
class TestExpenseReceiptDocument(TestExpenseSettlementCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.document_type_ticket = cls.env['l10n_latam.document.type'].create({
            'name': 'Ticket', 'code': '12', 'country_id': cls.company.account_fiscal_country_id.id,
        })
        cls.ruc = cls.env['l10n_latam.identification.type'].sudo().create({
            'name': 'RUC de prueba',
            'invoice_validation_document': [Command.set(cls.document_type_invoice.ids)],
        })
        cls.vendor.l10n_latam_identification_type_id = cls.ruc

    def test_only_accepted_document_types_are_offered(self):
        expense = self.env['hr.expense'].create(self.receipt_values(10.0))
        self.assertIn(self.document_type_invoice, expense.l10n_pe_available_document_type_ids)
        self.assertNotIn(self.document_type_ticket, expense.l10n_pe_available_document_type_ids)

        unrestricted = self.env['hr.expense'].create(self.receipt_values(10.0, vendor=self.vendor_2))
        self.assertIn(self.document_type_ticket, unrestricted.l10n_pe_available_document_type_ids)

    def test_not_accepted_document_type_blocks_approval(self):
        sheet = self.create_sheet([self.receipt_values(10.0, l10n_pe_document_type_id=self.document_type_ticket.id)])
        with self.assertRaisesRegex(UserError, 'no está permitido'):
            sheet.action_submit_sheet()

    def test_out_of_register_receipt_needs_no_document_type(self):
        """P1/P2 (OMNI 05/10): fuera del Registro de Compras no se exige el tipo de
        documento, aunque el proveedor tenga comprobantes restringidos."""
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        bill = self.create_receipt_bill(
            10.0, l10n_pe_in_purchase_register=False, l10n_pe_document_type_id=False,
        )
        self.assertRecordValues(bill, [{
            'state': 'posted', 'journal_id': self.non_register_journal.id, 'l10n_latam_document_type_id': False,
        }])

    def test_expense_without_receipt_posts_out_of_register(self):
        """Caso de los informes 34/35: el empleado (DNI) tiene comprobantes
        restringidos y el gasto no tiene proveedor ni tipo de documento."""
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        self.employee_partner.l10n_latam_identification_type_id = self.ruc
        bill = self.approve_and_post(self.create_sheet([self.no_receipt_values(40.0)]))
        self.assertRecordValues(bill, [{
            'state': 'posted', 'journal_id': self.non_register_journal.id, 'partner_id': self.employee_partner.id,
        }])

    def test_restricted_document_types_still_apply_in_the_register(self):
        bill = self.init_invoice('in_invoice', partner=self.vendor, amounts=[10.0])
        bill.l10n_latam_document_type_id = self.document_type_ticket
        with self.assertRaisesRegex(UserError, 'NO es el permitido'):
            bill.action_post()
        bill.journal_id = self.non_register_journal
        self.company.hr_expense_non_register_journal_id = self.non_register_journal
        bill.action_post()
        self.assertEqual(bill.state, 'posted')

    def test_accepted_document_type_posts_bill(self):
        bill = self.create_receipt_bill(10.0)
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(bill.l10n_latam_document_type_id, self.document_type_invoice)
