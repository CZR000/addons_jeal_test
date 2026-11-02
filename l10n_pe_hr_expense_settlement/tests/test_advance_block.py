from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .test_expense_rendition_flow import TestExpenseRenditionCommon


@tagged('post_install', '-at_install')
class TestAdvanceBlock(TestExpenseRenditionCommon):
    """Nota "Bloqueo de desembolsos con rendición pendiente" (20/10/2026)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.hr_expense_block_pending_advances = True
        cls.approver = new_test_user(cls.env, 'advance_block_approver', groups='approvals.group_approval_user',
                                     company_id=cls.company.id, company_ids=cls.company.ids)
        cls.treasury = new_test_user(
            cls.env, 'advance_block_treasury',
            groups='approvals.group_approval_user,l10n_pe_hr_expense_settlement.group_advance_block_override',
            company_id=cls.company.id, company_ids=cls.company.ids,
        )
        cls.category = cls.create_advance_category(cls, approver_ids=[
            Command.create({'user_id': cls.approver.id, 'required': True}),
        ])
        cls.document_type_invoice.internal_type = 'invoice'

    def new_request(self, amount=300.0):
        # El usuario de las pruebas no es de Aprobaciones: no vería los aprobadores.
        request = self.create_request(self.category, amount).sudo()
        self.assertEqual(request.approver_ids.user_id, self.approver)
        self.env.flush_all()
        return request

    def render(self, advance, amount, number='601'):
        sheet = self.create_sheet([self.receipt_values(amount, number=number)])
        sheet.l10n_pe_advance_line_id = advance
        self.approve_and_post(sheet)
        return sheet

    def test_pending_advance_blocks_new_disbursement(self):
        self.pay_request(self.new_request(500.0))
        request = self.new_request()
        self.assertIn('rendiciones pendientes', request.l10n_pe_pending_advance_warning,
                      'Aviso en pantalla antes de enviar')
        self.assertIn('500.00', request.l10n_pe_pending_advance_warning)
        with self.assertRaisesRegex(UserError, r'tiene rendiciones pendientes(.|\n)*saldo por rendir'):
            request.action_confirm()

    def test_everything_rendered_allows_new_disbursement(self):
        advance = self.create_advance(100.0)
        self.render(advance, 100.0)
        self.assertTrue(advance.reconciled)
        request = self.new_request()
        self.assertIs(request.l10n_pe_pending_advance_warning, False, 'Sin pendientes: sin aviso (no un recordset)')
        request.action_confirm()
        request.action_approve(request.approver_ids)
        self.assertEqual(request.request_status, 'approved')

    def test_block_lifts_when_rendered(self):
        advance = self.create_advance(100.0)
        request = self.new_request()
        with self.assertRaises(UserError):
            request.action_confirm()
        self.render(advance, 100.0)
        request.invalidate_recordset(['l10n_pe_pending_advance_warning'])
        self.assertFalse(request.l10n_pe_pending_advance_warning)
        request.action_confirm()

    def test_partial_rendition_shows_residual(self):
        advance = self.create_advance(100.0)
        self.render(advance, 60.0)
        self.assertEqual(advance.amount_residual, 40.0)
        with self.assertRaisesRegex(UserError, 'saldo por rendir .*40.00'):
            self.new_request().action_confirm()

    def test_pending_in_another_company(self):
        """La misma persona es empleado en otra empresa del grupo (mismo DNI)."""
        other = self.setup_other_company(name='JE-AL (bloqueo)')['company']
        other_account = self.env['account.account'].with_company(other).create({
            'code': '1413000', 'name': 'Entregas a rendir', 'account_type': 'asset_receivable', 'reconcile': True,
        })
        self.expense_employee.identification_id = '45678912'
        other_employee = self.env['hr.employee'].with_company(other).create({
            'name': self.expense_employee.name, 'company_id': other.id, 'identification_id': '45678912',
        })
        self.assertNotEqual(other_employee.work_contact_id, self.employee_partner)
        bank = self.env['account.journal'].with_company(other).search([('company_id', '=', other.id), ('type', '=', 'bank')], limit=1)
        move = self.env['account.move'].with_company(other).create({
            'move_type': 'entry', 'company_id': other.id, 'journal_id': bank.id, 'date': self.today,
            'line_ids': [
                Command.create({'account_id': other_account.id, 'partner_id': other_employee.work_contact_id.id,
                                'balance': 250.0}),
                Command.create({'account_id': bank.default_account_id.id, 'balance': -250.0}),
            ],
        })
        move.action_post()
        with self.assertRaisesRegex(UserError, 'JE-AL \\(bloqueo\\)'):
            self.new_request().action_confirm()

    def test_pending_with_the_dni_contact(self):
        """Caso OMNI (Oscar Huarcaya): el anticipo está a nombre de un contacto con el
        DNI como documento; el contacto de trabajo de la ficha no tiene documento."""
        self.expense_employee.identification_id = '42897102'
        dni_contact = self.env['res.partner'].create({'name': 'HUARCAYA OSCCO, OSCAR', 'vat': '42897102'})
        self.create_advance(660.0, partner=dni_contact)
        with self.assertRaisesRegex(UserError, '660.00'):
            self.new_request().action_confirm()

    def test_tolerance_days(self):
        # El bloqueo cuenta los días hasta hoy (las pruebas fechan los anticipos en 2022).
        self.create_advance(100.0, date=fields.Date.today() - timedelta(days=10))
        self.company.hr_expense_block_pending_days = 30
        self.new_request().action_confirm()
        self.company.hr_expense_block_pending_days = 5
        with self.assertRaises(UserError):
            self.new_request().action_confirm()

    def test_authorized_user_can_override_with_reason(self):
        self.create_advance(100.0)
        request = self.new_request()
        with self.assertRaisesRegex(UserError, 'Motivo de la autorización'):
            request.with_user(self.treasury).action_confirm()
        request.l10n_pe_block_override_reason = 'Viaje urgente a mina'
        with self.assertRaises(UserError, msg='Sin el grupo, el motivo no basta'):
            request.with_user(self.approver).action_confirm()
        request.with_user(self.treasury).sudo().action_confirm()
        self.assertEqual(request.l10n_pe_block_override_user_id, self.treasury)
        self.assertTrue(any('Viaje urgente a mina' in message.body for message in request.message_ids))
        request.action_approve(request.approver_ids)
        self.assertEqual(request.request_status, 'approved', 'La autorización vale para la aprobación')

    def test_manual_payment_to_employee_advance_account(self):
        self.create_advance(100.0)
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': self.employee_partner.id,
            'amount': 200.0, 'journal_id': self.bank_journal.id, 'destination_account_id': self.advance_account.id,
        })
        self.assertTrue(payment.l10n_pe_pending_advance_warning)
        with self.assertRaises(UserError):
            payment.action_post()
        # A un proveedor no aplica.
        vendor_payment = self.env['account.payment'].create({
            'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': self.vendor.id,
            'amount': 200.0, 'journal_id': self.bank_journal.id,
        })
        vendor_payment.action_post()

    def test_petty_cash_fund_does_not_count_by_default(self):
        petty_account = self.env['account.account'].create({
            'code': '141302', 'name': 'Caja chica', 'account_type': 'asset_receivable', 'reconcile': True,
        })
        self.company.hr_expense_petty_cash_account_id = petty_account
        self.create_advance(400.0, account=petty_account)
        self.new_request().action_confirm()
        self.company.hr_expense_block_include_petty_cash = True
        with self.assertRaises(UserError):
            self.new_request().action_confirm()

    def test_disabled(self):
        self.create_advance(100.0)
        self.company.hr_expense_block_pending_advances = False
        self.new_request().action_confirm()
