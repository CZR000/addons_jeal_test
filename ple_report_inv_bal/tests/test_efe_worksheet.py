from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEfeWorksheet(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.trade = cls.make_account(
            '12999997', 'EFE trade receivable', 'asset_receivable',
        )
        cls.other = cls.make_account(
            '16999997', 'EFE other receivable', 'asset_current',
        )

    @classmethod
    def make_account(cls, code, name, account_type):
        accounts = cls.env['account.account'].with_company(cls.env.company)
        while accounts.search([
            ('company_ids', 'in', cls.env.company.ids), ('code', '=', code),
        ], limit=1):
            code = str(int(code) + 1)
        return accounts.create({
            'name': name,
            'code': code,
            'account_type': account_type,
            'reconcile': account_type == 'asset_receivable',
            'company_ids': [Command.set(cls.env.company.ids)],
        })

    def worksheet(self, flows):
        report = self.env['ple.report.inv.bal.book'].new({
            'company_id': self.env.company.id,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        return report._efe_worksheet(
            flows, self.env['account.account'], {}, {},
        )

    def test_same_account_and_statement_line_combine_partner_categories(self):
        result = self.worksheet([
            (self.trade.id, False, 100.0, 0.0),
            (self.trade.id, True, 50.0, 0.0),
        ])
        detail = result['lines']['op_cobro_ventas']
        self.assertEqual(len(detail), 1)
        self.assertEqual(detail[0]['code'], self.trade.code)
        self.assertEqual(detail[0]['amount'], 150.0)
        self.assertEqual(result['rows'][0]['flow'], 150.0)

    def test_intercompany_classification_keeps_distinct_statement_lines(self):
        result = self.worksheet([
            (self.other.id, False, 30.0, 0.0),
            (self.other.id, True, 40.0, 0.0),
        ])
        self.assertEqual(result['lines']['op_otros_cobros'][0]['amount'], 30.0)
        self.assertEqual(result['lines']['inv_otros_cobros'][0]['amount'], 40.0)
        self.assertEqual(result['rows'][0]['flow'], 70.0)

    def test_receipts_and_payments_remain_separate(self):
        self.other.l10n_pe_cash_flow_activity = 'operation'
        result = self.worksheet([
            (self.other.id, False, 100.0, -20.0),
            (self.other.id, True, 50.0, -10.0),
        ])
        self.assertEqual(result['lines']['op_otros_cobros'][0]['amount'], 150.0)
        self.assertEqual(result['lines']['op_otros_pagos'][0]['amount'], -30.0)
        self.assertEqual(result['rows'][0]['flow'], 120.0)
