from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .test_expense_rendition_flow import TestExpenseRenditionCommon


@tagged('post_install', '-at_install')
class TestExpensePettyCashP14P17(TestExpenseRenditionCommon):
    """Pedidos de la prueba de caja chica en OMNI (13/10/2026): P14 a P17."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.petty_account = cls.env['account.account'].create({
            'code': '141302', 'name': 'Entregas a rendir - Caja chica', 'account_type': 'asset_receivable',
            'reconcile': True,
        })
        cls.company.hr_expense_petty_cash_account_id = cls.petty_account
        cls.approver = new_test_user(cls.env, 'petty_cash_approver', groups='approvals.group_approval_user',
                                     company_id=cls.company.id, company_ids=cls.company.ids)
        cls.category = cls.create_advance_category(cls, 'petty_cash', approver_ids=[
            Command.create({'user_id': cls.approver.id, 'required': True}),
        ])
        # La factura del comprobante es una "Factura" (l10n_latam valida el tipo contra la NC).
        cls.document_type_invoice.internal_type = 'invoice'

    def pay_fund(self, amount):
        payment = self.pay_request(self.create_request(self.category, amount))
        return payment.move_id.line_ids.filtered(lambda line: line.account_id == self.petty_account)

    def rendition(self, fund, amount, number='501'):
        sheet = self.create_sheet([self.receipt_values(amount, number=number)])
        sheet.l10n_pe_advance_line_id = fund
        self.approve_and_post(sheet)
        return sheet

    # P14 ------------------------------------------------------------------ #

    def test_reset_posted_petty_cash_report(self):
        """P14: restablecer un informe liquidado anula la factura y la liquidación, sin error."""
        fund = self.pay_fund(800.0)
        sheet = self.rendition(fund, 100.0)
        bill = sheet.account_move_ids
        settlement = bill.hr_expense_settlement_move_ids
        self.assertEqual(fund.amount_residual, 700.0)

        sheet.action_reset_expense_sheets()

        self.assertEqual(sheet.state, 'draft')
        self.assertEqual(bill.state, 'cancel')
        self.assertEqual(settlement.state, 'cancel')
        self.assertEqual(fund.amount_residual, 800.0, 'El fondo recupera su saldo')
        self.assertFalse(sheet.account_move_ids)
        # El comprobante se puede volver a rendir.
        self.approve_and_post(sheet)
        self.assertEqual(sheet.account_move_ids.state, 'posted')

    def test_reset_in_closed_period_warns(self):
        fund = self.pay_fund(800.0)
        sheet = self.rendition(fund, 100.0)
        self.company.fiscalyear_lock_date = sheet.account_move_ids.date
        with self.assertRaisesRegex(UserError, 'periodo cerrado'):
            sheet.action_reset_expense_sheets()

    # P15 y P16 ------------------------------------------------------------ #

    def test_replenish_request_has_the_category_approvers(self):
        """P16: la solicitud de reposición nace con el aprobador de la categoría y se puede enviar.
        P15: el informe muestra la solicitud y la abre."""
        fund = self.pay_fund(800.0)
        sheet = self.rendition(fund, 50.0)
        action = sheet.action_l10n_pe_replenish_fund()
        request = self.env['approval.request'].browse(action['res_id'])
        self.assertEqual(request.request_owner_id, self.expense_user_employee)
        self.assertEqual(request.approver_ids.user_id, self.approver)
        request.action_confirm()
        self.assertEqual(request.request_status, 'pending')

        status = dict(request._fields['request_status']._description_selection(self.env))['pending']
        self.assertEqual(sheet.l10n_pe_replenish_request_label, f'{request.name} – {status}')
        self.assertEqual(sheet.action_l10n_pe_open_replenish_request()['res_id'], request.id)

    def test_owner_is_not_an_approver_of_the_replenishment(self):
        """P16: el propietario no puede aprobar su propia reposición; si es el único aprobador, se avisa."""
        fund = self.pay_fund(800.0)
        sheet = self.rendition(fund, 50.0)
        self.category.approver_ids = [Command.clear(), Command.create({'user_id': self.expense_user_employee.id})]
        # assertRaises (no assertRaisesRegex) deshace lo creado, como la transacción en la interfaz.
        with self.assertRaises(UserError) as error:
            sheet.action_l10n_pe_replenish_fund()
        self.assertIn('no tiene otro aprobador', error.exception.args[0])
        self.assertFalse(sheet.l10n_pe_replenish_request_ids, 'No queda una solicitud sin aprobador')

        self.category.approver_ids = [Command.create({'user_id': self.approver.id})]
        request = self.env['approval.request'].browse(sheet.action_l10n_pe_replenish_fund()['res_id'])
        self.assertEqual(request.approver_ids.user_id, self.approver, 'Sin el propietario')

    # P17 ------------------------------------------------------------------ #

    def test_petty_cash_uses_its_own_account_and_shows_the_total_balance(self):
        """P17 (a) y (c): el fondo va a su cuenta propia y el saldo total suma todas las líneas."""
        self.assertNotIn(self.petty_account, self.company._get_hr_expense_advance_accounts(),
                         'La cuenta de caja chica no es una entrega a rendir')
        fund = self.pay_fund(800.0)
        self.assertEqual(fund.account_id, self.petty_account)
        sheet = self.rendition(fund, 200.0)
        self.assertEqual(sheet.l10n_pe_petty_cash_balance, 600.0)

        request = self.env['approval.request'].browse(sheet.action_l10n_pe_replenish_fund()['res_id'])
        self.pay_request(request)
        self.assertEqual(len(self.expense_employee._l10n_pe_get_petty_cash_lines(self.company)), 2,
                         'La reposición es una línea nueva')
        sheet.invalidate_recordset(['l10n_pe_petty_cash_balance'])
        self.assertEqual(sheet.l10n_pe_petty_cash_balance, 800.0)
        self.assertEqual(self.expense_employee.l10n_pe_petty_cash_balance, 800.0)

    def test_means_of_payment_follows_the_journal(self):
        """P17 (b): banco con 001, caja con efectivo (008)."""
        codes = {code.code: code for code in self.env['payment.methods.codes'].search([('code', 'in', ('001', '003', '008'))])}
        cash = self.company_data['default_journal_cash']
        self.category.default_payment_journal_id = cash
        self.assertEqual(self.category._get_means_payment(cash), codes['008'])
        self.assertEqual(self.category._get_means_payment(self.bank_journal), codes['001'])
        with self.assertRaisesRegex(ValidationError, 'no corresponde al diario'):
            self.category.default_means_payment_id = codes['001']
        self.category.default_payment_journal_id = self.bank_journal
        self.category.default_means_payment_id = codes['003']
        self.assertEqual(self.category._get_means_payment(self.bank_journal), codes['003'])
        self.assertEqual(self.category._get_means_payment(cash), codes['008'], 'Pago desde una caja: efectivo')
