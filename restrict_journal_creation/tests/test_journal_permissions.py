from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged, new_test_user
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestJournalPermissions(TransactionCase):
    def setUp(self):
        super().setUp()
        self.user = new_test_user(self.env, login='test_journal_permission', groups='account.group_account_manager')
        self.group = self.env.ref('restrict_journal_creation.group_allow_create_account_journal')
        self.user.groups_id = self.user.groups_id - self.group
        self.values = {'name': 'Test journal restriction', 'code': 'TRJ', 'type': 'general', 'company_id': self.env.company.id}

    def test_normal_user_without_group_is_denied(self):
        with self.assertRaises(AccessError):
            self.env['account.journal'].with_user(self.user).create(self.values)

    def test_group_member_can_create(self):
        self.user.write({'groups_id': [Command.link(self.group.id)]})
        journal = self.env['account.journal'].with_user(self.user).create(self.values)
        self.assertEqual(journal.company_id, self.env.company)

    def test_internal_sudo_can_create(self):
        journal = self.env['account.journal'].with_user(self.user).sudo().create(self.values)
        self.assertEqual(journal.company_id, self.env.company)
        self.assertNotIn(self.group, self.user.groups_id)
