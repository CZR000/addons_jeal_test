from odoo import Command, fields
from odoo.addons.hr_expense.tests.common import TestExpenseCommon


class TestExpenseSettlementCommon(TestExpenseCommon):

    @classmethod
    def setup_independent_company(cls, **kwargs):
        group = cls.env.ref('restrict_journal_creation.group_allow_create_account_journal', raise_if_not_found=False)
        if group:
            cls.env.user.write({'groups_id': [(4, group.id)]})
        return super().setup_independent_company(**kwargs)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.employee_partner = cls.expense_employee.work_contact_id
        cls.vendor = cls.partner_a
        cls.vendor_2 = cls.partner_b
        cls.today = fields.Date.to_date(cls.frozen_today)

        cls.document_type_invoice = cls.env['l10n_latam.document.type'].create({
            'name': 'Factura',
            'code': '01',
            'country_id': cls.company.account_fiscal_country_id.id,
        })
        cls.advance_account = cls.env['account.account'].create({
            'code': '141300',
            'name': 'Personal - Entregas a rendir cuenta',
            'account_type': 'asset_receivable',
            'reconcile': True,
        })
        cls.non_register_journal = cls.env['account.journal'].create({
            'name': 'Gastos sin sustento',
            'code': 'GTOSS',
            'type': 'purchase',
        })
        cls.company.write({
            'hr_expense_settlement_journal_id': cls.company_data['default_journal_misc'].id,
            'hr_expense_advance_account_ids': [Command.set(cls.advance_account.ids)],
            # Las pruebas del asistente liquidan a mano; la automática tiene las suyas.
            'hr_expense_auto_settle': False,
            # Varias pruebas dan más de un anticipo al mismo empleado; el bloqueo tiene las suyas.
            'hr_expense_block_pending_advances': False,
        })

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def create_advance(self, amount, date=None, currency=None, amount_currency=None, partner=None, account=None):
        """Anticipo al empleado: Debe 14 (empleado) / Haber banco."""
        currency = currency or self.company.currency_id
        amount_currency = amount if amount_currency is None else amount_currency
        account = account or self.advance_account
        bank_account = self.company_data['default_journal_bank'].default_account_id
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': date or self.today,
            'journal_id': self.company_data['default_journal_misc'].id,
            'line_ids': [
                Command.create({
                    'name': 'Entrega a rendir',
                    'account_id': account.id,
                    'partner_id': (partner or self.employee_partner).id,
                    'currency_id': currency.id,
                    'amount_currency': amount_currency,
                    'balance': amount,
                }),
                Command.create({
                    'name': 'Entrega a rendir',
                    'account_id': bank_account.id,
                    'currency_id': currency.id,
                    'amount_currency': -amount_currency,
                    'balance': -amount,
                }),
            ],
        })
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == account)

    def receipt_values(self, amount, vendor=None, series='F001', number='123', **values):
        return {
            'name': f'Comprobante {series}-{number}',
            'employee_id': self.expense_employee.id,
            'product_id': self.product_c.id,
            'total_amount_currency': amount,
            'tax_ids': [Command.clear()],
            'date': self.frozen_today,
            'company_id': self.company.id,
            'currency_id': self.company.currency_id.id,
            'payment_mode': 'own_account',
            'vendor_id': (vendor or self.vendor).id,
            'l10n_pe_document_type_id': self.document_type_invoice.id,
            'l10n_pe_document_series': series,
            'l10n_pe_document_number': number,
            **values,
        }

    def no_receipt_values(self, amount, **values):
        """Gasto sin comprobante de proveedor (p.ej. movilidad sin sustento)."""
        return {
            **self.receipt_values(amount),
            'vendor_id': False,
            'l10n_pe_in_purchase_register': False,
            'l10n_pe_document_type_id': False,
            'l10n_pe_document_series': False,
            'l10n_pe_document_number': False,
            **values,
        }

    def create_sheet(self, expense_values_list):
        return self.env['hr.expense.sheet'].create({
            'name': 'Rendición',
            'employee_id': self.expense_employee.id,
            'company_id': self.company.id,
            'expense_line_ids': [Command.create(values) for values in expense_values_list],
        })

    def approve_and_post(self, sheet):
        sheet.action_submit_sheet()
        sheet.action_approve_expense_sheets()
        sheet.action_sheet_move_post()
        return sheet.account_move_ids

    def create_receipt_bill(self, amount, **values):
        return self.approve_and_post(self.create_sheet([self.receipt_values(amount, **values)]))

    def open_settlement_wizard(self, bill, **values):
        action = bill.action_open_hr_expense_settlement_wizard()
        wizard = self.env[action['res_model']].with_context(action['context']).create({
            'date': self.today,
            **values,
        })
        return wizard
