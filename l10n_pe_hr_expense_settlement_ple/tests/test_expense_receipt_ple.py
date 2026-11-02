from odoo.tests import tagged

from odoo.addons.l10n_pe_hr_expense_settlement.tests.common import TestExpenseSettlementCommon


@tagged('post_install', '-at_install')
class TestExpenseReceiptPle(TestExpenseSettlementCommon):

    def test_document_types_of_other_companies_are_not_offered(self):
        journal_2 = self.company_data_2['default_journal_purchase']
        foreign_type = self.env['l10n_latam.document.type'].create({
            'name': 'Factura otra compañía', 'code': '01',
            'country_id': self.company.account_fiscal_country_id.id,
            'account_journal_id': journal_2.id,
        })
        allowed = self.env['hr.expense'].create(self.receipt_values(10.0)).l10n_pe_available_document_type_ids
        self.assertIn(self.document_type_invoice, allowed)
        self.assertNotIn(foreign_type, allowed)
