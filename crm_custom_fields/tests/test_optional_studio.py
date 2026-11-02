from odoo.tests import TransactionCase, tagged
from odoo.addons.crm_custom_fields import post_init_hook


@tagged('post_install', '-at_install')
class TestOptionalStudio(TransactionCase):
    def test_loss_fields_render(self):
        view = self.env.ref('crm_custom_fields.crm_lead_loss_fields_form')
        self.assertTrue(view._get_combined_arch().xpath("//field[@name='x_loss_category']"))

    def test_studio_parent_without_old_loss_fields(self):
        xmlid = 'studio_customization.odoo_studio_crm_lead_dd0d698a-3c65-4e35-bf29-693a91259456'
        studio = self.env.ref(xmlid, raise_if_not_found=False)
        if not studio:
            studio = self.env['ir.ui.view'].create({
                'name': 'CRM Studio compatibility fixture', 'model': 'crm.lead',
                'inherit_id': self.env.ref('crm.crm_lead_view_form').id,
                'arch_db': '<xpath expr="//sheet" position="attributes"><attribute name="string">Opportunity</attribute></xpath>',
            })
            module, name = xmlid.split('.', 1)
            self.env['ir.model.data'].create({
                'module': module, 'name': name, 'model': 'ir.ui.view', 'res_id': studio.id,
            })
        self.env['crm.lead']._configure_loss_form_view()
        view = self.env.ref('crm_custom_fields.crm_lead_loss_fields_form')
        self.assertEqual(view.inherit_id, studio)
        self.assertTrue(view._get_combined_arch().xpath("//field[@name='x_loss_detail_price']"))

    def test_migration_preserves_existing_custom_values(self):
        lead = self.env['crm.lead'].create({
            'name': 'Loss migration regression', 'x_loss_category': 'price',
            'x_loss_detail_price': 'high_price',
        })
        self.env.flush_all()
        post_init_hook(self.env)
        lead.invalidate_recordset()
        self.assertEqual(lead.x_loss_category, 'price')
        self.assertEqual(lead.x_loss_detail_price, 'high_price')
