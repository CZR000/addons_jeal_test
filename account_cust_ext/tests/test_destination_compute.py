from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDestinationCompute(TransactionCase):
    def test_destination_priority_and_display_compute(self):
        account_model = self.env["account.account"]
        accounts = account_model.create([
            {"name": "Warning regression source", "code": "WARN1801", "account_type": "expense", "has_destination_account": True},
            {"name": "Warning regression destination A", "code": "WARN1802", "account_type": "expense"},
            {"name": "Warning regression destination B", "code": "WARN1803", "account_type": "expense"},
        ])
        plan = self.env["account.analytic.plan"].create({"name": "Warning regression plan"})
        analytics = self.env["account.analytic.account"].create([
            {"name": "Destination A", "plan_id": plan.id, "company_id": self.env.company.id,
             "has_destination_account": True, "destination_account_id": accounts[1].id},
            {"name": "Destination B", "plan_id": plan.id, "company_id": self.env.company.id,
             "has_destination_account": True, "destination_account_id": accounts[2].id},
        ])
        line = self.env["account.move.line"].new({
            "company_id": self.env.company.id, "account_id": accounts[0].id,
            "analytic_distribution": {str(analytics[1].id): 60, str(analytics[0].id): 40},
        })
        line._compute_destination_account_id()
        self.assertEqual(line.destination_account_id, accounts[2])
        line._compute_destination_account_ids()
        self.assertEqual(set(line.destination_account_ids.ids), set(accounts[1:].ids))
        self.assertEqual(line.destination_account_id, accounts[2])
        line.analytic_distribution = {}
        line._compute_destination_account_id()
        line._compute_destination_account_ids()
        self.assertFalse(line.destination_account_id)
        self.assertFalse(line.destination_account_ids)

    def test_group_change_recomputes_destination_flag(self):
        group = self.env["account.group"].create({
            "name": "Warning regression group", "code_prefix_start": "WRN18",
            "code_prefix_end": "WRN18", "company_id": self.env.company.id,
            "has_destination_account": False,
        })
        account = self.env["account.account"].create({
            "name": "Warning regression grouped", "code": "WRN1801", "account_type": "expense",
        })
        self.assertEqual(account.group_id, group)
        self.assertIn(account, self.env["account.account"].search([("group_id", "in", group.ids)]))
        self.assertFalse(account.has_destination_account)
        group.has_destination_account = True
        self.assertTrue(account.has_destination_account)
        group.has_destination_account = False
        self.assertFalse(account.has_destination_account)
