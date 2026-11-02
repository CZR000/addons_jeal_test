from odoo.tests import tagged

from odoo.addons.sale_commission_ext.tests.test_sale_commission_currency import TestSaleCommissionCurrency


@tagged('post_install', '-at_install')
class TestSaleCommissionExchangeRate(TestSaleCommissionCurrency):

    def test_sale_rate_is_used(self):
        Rate = self.env['res.currency.rate']
        Rate.create({'name': '2024-02-20', 'rate': 4.0, 'currency_id': self.foreign.id,
                     'company_id': self.company.id, 'exchange_rate': 'sale'})
        Rate.create({'name': '2024-02-20', 'rate': 5.0, 'currency_id': self.foreign.id,
                     'company_id': self.company.id, 'exchange_rate': 'purchase'})
        self.plan.currency_id = self.foreign
        self.plan.action_approve()
        self.invoice(100.0)
        self.assertAlmostEqual(self.achieved()[0], 400.0)
