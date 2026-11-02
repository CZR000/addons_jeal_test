import datetime

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.sale_commission.tests.test_sale_commission_common import TestSaleCommissionCommon


@tagged('post_install', '-at_install')
@freeze_time('2024-02-20')
class TestSaleCommissionCurrency(TestSaleCommissionCommon):
    """Compañía en USD; "moneda extranjera" a 2 unidades por 1 USD."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.foreign = cls.setup_other_currency('EUR', rates=[('2000-01-01', 2.0)])
        cls.plan = cls.commission_plan_user
        cls.plan.write({'type': 'achieve', 'periodicity': 'month'})
        cls.plan.achievement_ids = [Command.clear(), Command.create({'type': 'amount_invoiced', 'rate': 1.0})]

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def invoice(self, amount, currency=None, move_type='out_invoice', post=True, date='2024-02-20'):
        move = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.partner.id,
            'invoice_user_id': self.commission_user_1.id,
            'invoice_date': date,
            'currency_id': (currency or self.company.currency_id).id,
            'invoice_line_ids': [Command.create({
                'product_id': self.commission_product_1.id,
                'quantity': 1,
                'price_unit': amount,
                'tax_ids': [Command.clear()],
            })],
        })
        if post:
            move.action_post()
        return move

    def achieved(self, plan=None):
        self.env.invalidate_all()
        lines = self.env['sale.commission.achievement.report'].search([('plan_id', '=', (plan or self.plan).id)])
        return sum(lines.mapped('achieved')), lines.currency_id

    def commission_lines(self, plan=None):
        self.env.invalidate_all()
        return self.env['sale.commission.report'].search([
            ('plan_id', '=', (plan or self.plan).id), ('user_id', '=', self.commission_user_1.id),
        ])

    # -------------------------------------------------------------------------
    # Solo facturas publicadas
    # -------------------------------------------------------------------------

    def test_draft_invoices_are_not_achievements(self):
        self.plan.action_approve()
        draft = self.invoice(1000.0, post=False)
        self.assertEqual(self.achieved()[0], 0.0)

        draft.action_post()
        self.assertEqual(self.achieved()[0], 1000.0)

        draft.button_draft()
        draft.button_cancel()
        self.assertEqual(self.achieved()[0], 0.0)

    # -------------------------------------------------------------------------
    # Plan en la moneda de la compañía: igual que el estándar
    # -------------------------------------------------------------------------

    def test_company_currency_plan_converts_foreign_invoices(self):
        self.plan.action_approve()
        self.invoice(1000.0, currency=self.foreign)
        achieved, currency = self.achieved()
        self.assertEqual(currency, self.company.currency_id)
        self.assertAlmostEqual(achieved, 500.0)

    def test_company_currency_plan_uses_booked_amount(self):
        """Tipo de cambio forzado en la factura: se usa el importe contabilizado."""
        self.plan.action_approve()
        move = self.invoice(1000.0, currency=self.foreign, post=False)
        move.invoice_currency_rate = 2.5
        move.action_post()
        self.assertAlmostEqual(self.achieved()[0], 400.0)

    def test_zero_rate_invoice_does_not_break_report(self):
        """Facturas de importe cero con invoice_currency_rate en 0 (datos de jeal)."""
        self.plan.action_approve()
        zero = self.invoice(0.0, currency=self.foreign)
        self.env.cr.execute('UPDATE account_move SET invoice_currency_rate = 0 WHERE id = %s', [zero.id])
        self.invoice(1000.0, currency=self.foreign)
        self.assertAlmostEqual(self.achieved()[0], 500.0)
        self.assertTrue(self.commission_lines())

    # -------------------------------------------------------------------------
    # Plan en moneda extranjera
    # -------------------------------------------------------------------------

    def test_foreign_plan_invoice_in_plan_currency_is_exact(self):
        self.plan.currency_id = self.foreign
        self.plan.action_approve()
        self.invoice(1234.56, currency=self.foreign)
        achieved, currency = self.achieved()
        self.assertEqual(currency, self.foreign)
        self.assertAlmostEqual(achieved, 1234.56)

    def test_foreign_plan_converts_company_currency_invoice(self):
        self.plan.currency_id = self.foreign
        self.plan.action_approve()
        self.invoice(1000.0)
        self.assertAlmostEqual(self.achieved()[0], 2000.0)

    def test_foreign_plan_uses_rate_of_the_invoice_date(self):
        self.env['res.currency.rate'].create({
            'name': '2024-02-15', 'rate': 4.0, 'currency_id': self.foreign.id, 'company_id': self.company.id,
        })
        self.plan.currency_id = self.foreign
        self.plan.action_approve()
        self.invoice(100.0, date='2024-02-10')
        self.invoice(100.0, date='2024-02-20')
        self.assertAlmostEqual(self.achieved()[0], 100.0 * 2 + 100.0 * 4)

    def test_foreign_plan_refund_is_negative(self):
        self.plan.currency_id = self.foreign
        self.plan.action_approve()
        self.invoice(1000.0, currency=self.foreign)
        self.invoice(300.0, currency=self.foreign, move_type='out_refund')
        self.assertAlmostEqual(self.achieved()[0], 700.0)

    def test_foreign_plan_sale_orders(self):
        self.plan.currency_id = self.foreign
        self.plan.achievement_ids = [Command.clear(), Command.create({'type': 'amount_sold', 'rate': 1.0})]
        self.plan.action_approve()
        foreign_pricelist = self.env['product.pricelist'].create({'name': 'EUR', 'currency_id': self.foreign.id})
        for pricelist in (foreign_pricelist, self.env['product.pricelist']):
            order = self.env['sale.order'].create({
                'partner_id': self.partner.id,
                'user_id': self.commission_user_1.id,
                'pricelist_id': pricelist.id,
                'order_line': [Command.create({'product_id': self.commission_product_1.id, 'price_unit': 100.0})],
            })
            order.action_confirm()
        # 100 EUR exactos + 100 USD a 2 EUR/USD
        self.assertAlmostEqual(self.achieved()[0], 300.0)

    def test_manual_adjustments_are_converted_to_plan_currency(self):
        self.plan.achievement_ids = [Command.clear(), Command.create({'type': 'amount_invoiced', 'rate': 1.0})]
        self.plan.action_approve()
        adjustment = self.env['sale.commission.achievement'].create({
            'user_id': self.commission_user_1.id,
            'team_id': self.team_commission.id,
            'type': 'amount_invoiced',
            'amount': 100.0,
            'currency_id': self.foreign.id,
            'date': '2024-02-20',
        })
        self.assertAlmostEqual(self.achieved()[0], 50.0, msg='100 EUR = 50 USD (el estándar daba 200)')

        foreign_plan = self.plan.copy({'name': 'Plan EUR', 'currency_id': self.foreign.id})
        foreign_plan.action_approve()
        self.assertAlmostEqual(self.achieved(foreign_plan)[0], 100.0)

        adjustment.currency_id = self.company.currency_id
        self.assertAlmostEqual(self.achieved(foreign_plan)[0], 200.0)

    def test_target_and_commission_in_plan_currency(self):
        self.plan.write({'type': 'target', 'currency_id': self.foreign.id, 'commission_amount': 500.0})
        february = self.plan.target_ids.filtered(lambda target: target.date_from == datetime.date(2024, 2, 1))
        february.amount = 1000.0
        self.plan.action_approve()
        self.invoice(1000.0, currency=self.foreign)

        line = self.commission_lines().filtered(lambda l: l.target_id == february)
        self.assertEqual(line.currency_id, self.foreign)
        self.assertAlmostEqual(line.achieved, 1000.0)
        self.assertAlmostEqual(line.target_amount, 1000.0)
        self.assertAlmostEqual(line.commission, 500.0, msg='Objetivo alcanzado al 100%: comisión completa en EUR')

    def test_periods_without_achievements_show_plan_currency(self):
        self.plan.currency_id = self.foreign
        self.plan.action_approve()
        lines = self.commission_lines()
        self.assertEqual(len(lines), 12)
        self.assertEqual(lines.currency_id, self.foreign)
        self.assertEqual(lines.company_id, self.company)

    # -------------------------------------------------------------------------
    # Moneda del plan
    # -------------------------------------------------------------------------

    def test_plan_currency_defaults_to_company_currency(self):
        plan = self.env['sale.commission.plan'].create({'name': 'Nuevo', 'company_id': self.company.id})
        self.assertEqual(plan.currency_id, self.company.currency_id)

    def test_currency_cannot_change_after_approval(self):
        self.plan.action_approve()
        with self.assertRaises(UserError):
            self.plan.currency_id = self.foreign
        self.plan.currency_id = self.company.currency_id  # sin cambio real: permitido
