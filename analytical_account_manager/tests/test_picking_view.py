from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAnalyticPickingView(TransactionCase):
    def test_analytic_lines_use_odoo18_quantity(self):
        view = self.env['stock.picking'].get_view(
            self.env.ref('stock.view_picking_form').id, 'form',
        )
        arch = etree.fromstring(view['arch'])
        page = arch.xpath("//page[@name='analytic_account_page']")
        self.assertTrue(page)
        self.assertTrue(page[0].xpath(".//field[@name='quantity']"))
        self.assertFalse(page[0].xpath(".//field[@name='qty_done']"))
