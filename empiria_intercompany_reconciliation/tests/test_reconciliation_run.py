import base64
import io
import zipfile
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestIcReconciliationRun(AccountTestInvoicingCommon):
    @classmethod
    def setup_independent_company(cls, **kwargs):
        # A chart creates journals; respect optional customer access restrictions.
        group = cls.env.ref('restrict_journal_creation.group_allow_create_account_journal', raise_if_not_found=False)
        if group:
            cls.env.user.write({'groups_id': [(4, group.id)]})
        return super().setup_independent_company(**kwargs)

    """Flujo completo en Odoo: generar, resumen, detalle, revisar, emparejar a
    mano, exportar y ejecución diaria."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b_data = cls.setup_other_company(name='Connected (test)')
        cls.company_a = cls.company_data['company']
        cls.company_b = cls.company_b_data['company']
        cls.company_a.write({'vat': '20552711867', 'name': 'JE-AL ENTERPRISES (test)'})
        cls.company_b.write({'vat': '20611680067'})
        cls.config = cls.env['ic.reconciliation.config'].get_config()
        receivable = cls.company_data['default_account_receivable'].code[:2]
        payable = cls.company_data['default_account_payable'].code[:2]
        cls.config.write({
            'company_ids': [Command.set((cls.company_a | cls.company_b).ids)],
            'receivable_prefixes': receivable,
            'payable_prefixes': payable,
            'responsible_user_id': cls.env.user.id,
        })
        cls.partner_b_in_a = cls.company_b.partner_id
        cls.partner_a_in_b = cls.company_a.partner_id
        cls.today = fields.Date.today()

    # Helpers ------------------------------------------------------------ #

    def set_number(self, move, number, field):
        self.env.cr.execute(f'UPDATE account_move SET {field} = %s WHERE id = %s', [number, move.id])
        move.invalidate_recordset([field])

    def sale(self, amount, number):
        invoice = self.init_invoice('out_invoice', partner=self.partner_b_in_a, amounts=[amount], post=True,
                                    company=self.company_a, taxes=self.env['account.tax'], invoice_date=self.today)
        self.set_number(invoice, number, 'name')
        return invoice

    def purchase(self, amount, number):
        bill = self.env['account.move'].with_company(self.company_b).create({
            'move_type': 'in_invoice', 'partner_id': self.partner_a_in_b.id, 'invoice_date': self.today,
            'company_id': self.company_b.id, 'ref': number,
            'invoice_line_ids': [Command.create({'name': 'Servicio', 'quantity': 1, 'price_unit': amount, 'tax_ids': []})],
        })
        bill.action_post()
        return bill

    def payment_entry(self, company_data, partner, account, amount, label='Pago', date=None):
        move = self.env['account.move'].with_company(company_data['company']).create({
            'move_type': 'entry', 'journal_id': company_data['default_journal_bank'].id, 'date': date or self.today,
            'company_id': company_data['company'].id,
            'line_ids': [
                Command.create({'name': label, 'account_id': account.id, 'partner_id': partner.id, 'balance': amount}),
                Command.create({'name': label, 'account_id': company_data['default_journal_bank'].default_account_id.id,
                                'balance': -amount}),
            ],
        })
        move.action_post()
        return move

    def generate(self, **values):
        wizard = self.env['ic.reconciliation.generate'].create({'date_to': self.today, **values})
        action = wizard.action_generate()
        run = self.env['ic.reconciliation.run'].search([], limit=1)
        self.assertEqual(run.state, 'done')
        self.assertTrue(run.control_ok, 'Control en 0 en todos los pares')
        return run, action

    # Pruebas ------------------------------------------------------------ #

    def test_generate_summary_and_detail(self):
        self.sale(1000.0, 'F001-00000010')
        self.purchase(1000.0, 'F001-10')
        payment = self.payment_entry(self.company_data, self.partner_b_in_a,
                                     self.company_data['default_account_receivable'], -400.0, 'Cobro factura F001-10')
        run, action = self.generate()

        self.assertEqual(action['res_model'], 'ic.reconciliation.pair')
        pair = run.pair_ids
        self.assertEqual(len(pair), 1)
        self.assertRecordValues(pair, [{
            'company_a_id': self.company_a.id, 'company_b_id': self.company_b.id, 'block': 'a_receivable',
            'total_difference': -400.0,
            'balance_a': 600.0, 'balance_b': -1000.0, 'difference': -400.0, 'state': 'pending',
            'pending_count': 1, 'amount_payment': -400.0, 'control': 0.0,
        }])
        line = run.line_ids
        self.assertRecordValues(line, [{
            'category': 'payment', 'company_id': self.company_a.id, 'move_id': payment.id,
            'effect_pen': -400.0, 'status': 'pending', 'rule': 15,
        }])
        self.assertIn('Registrar el pago o cobro en la otra empresa', line.action_hint)
        self.assertEqual(line.action_open_document()['res_id'], payment.id)

    def test_review_is_kept_until_the_amount_changes(self):
        """Caso 11: revisar con comentario, volver a generar; si cambia el importe, vuelve a pendiente."""
        payment = self.payment_entry(self.company_data, self.partner_b_in_a,
                                     self.company_data['default_account_receivable'], 250.0)
        run, _action = self.generate()
        wizard = self.env['ic.reconciliation.review.wizard'].with_context(
            **run.line_ids.action_mark_reviewed()['context']).create({'comment': 'Devolución confirmada con tesorería'})
        wizard.action_confirm()
        self.assertEqual(run.line_ids.status, 'reviewed')
        self.assertRecordValues(run.pair_ids, [{'reviewed_count': 1, 'pending_count': 0, 'state': 'reviewed'}])

        run2, _action = self.generate()
        self.assertEqual(run2.line_ids.status, 'reviewed')
        self.assertEqual(run2.line_ids.review_comment, 'Devolución confirmada con tesorería')
        self.assertEqual(run2.reviewed_line_count, 1)

        payment.button_draft()
        payment.write({'line_ids': [
            Command.update(payment.line_ids.filtered('partner_id').id, {'balance': 260.0}),
            Command.update(payment.line_ids.filtered(lambda l: not l.partner_id).id, {'balance': -260.0}),
        ]})
        payment.action_post()
        run3, _action = self.generate()
        self.assertEqual(run3.line_ids.status, 'pending', 'Cambió el importe: la revisión ya no vale')

        with self.assertRaisesRegex(UserError, 'comentario es obligatorio'):
            self.env['ic.reconciliation.review.wizard'].create({'line_ids': run3.line_ids.ids, 'comment': '  '}).action_confirm()

    def test_manual_match(self):
        """Caso 12: unir dos movimientos con diferencia y motivo."""
        self.payment_entry(self.company_data, self.partner_b_in_a, self.company_data['default_account_receivable'], -1000.0)
        self.payment_entry(self.company_b_data, self.partner_a_in_b, self.company_b_data['default_account_payable'], 977.0)
        run, _action = self.generate()
        self.assertEqual(sorted(run.line_ids.mapped('category')), ['payment', 'payment'])

        context = run.line_ids.action_manual_match()['context']
        wizard = self.env['ic.reconciliation.match.wizard'].with_context(**context).create({'reason': 'commission'})
        self.assertEqual(wizard.difference_pen, -23.0)
        with self.assertRaisesRegex(UserError, 'explicación es obligatoria'):
            wizard.action_confirm()
        wizard.reason_note = 'Comisión bancaria'
        wizard.action_confirm()
        self.assertEqual(set(run.line_ids.mapped('status')), {'manual'})
        self.assertRecordValues(run.pair_ids, [{'amount_payment': 0.0, 'amount_manual_match': -23.0, 'control': 0.0}])

        # P2: deshacer devuelve las líneas de la ejecución a pendiente al instante.
        run.line_ids[0].action_undo_manual_match()
        self.assertEqual(sorted(run.line_ids.mapped('category')), ['payment', 'payment'])
        self.assertEqual(set(run.line_ids.mapped('status')), {'pending'})
        self.assertRecordValues(run.pair_ids, [{'amount_payment': -23.0, 'amount_manual_match': 0.0, 'pending_count': 2,
                                                'control': 0.0}])
        self.assertIn('Emparejamiento deshecho', run.line_ids[0].note)

        wizard = self.env['ic.reconciliation.match.wizard'].with_context(**context).create(
            {'reason': 'commission', 'reason_note': 'Comisión bancaria'})
        wizard.action_confirm()
        run2, _action = self.generate()
        self.assertEqual(set(run2.line_ids.mapped('category')), {'manual_match'})
        self.assertIn('Comisión bancaria', run2.line_ids[0].note)

        run2.line_ids[0].action_undo_manual_match()
        self.assertEqual(run2.line_ids.status, 'pending', 'También la línea que armó el motor')
        self.assertEqual(run2.line_ids.category, 'payment')
        self.assertRecordValues(run2.pair_ids, [{'amount_manual_match': 0.0, 'pending_count': 1, 'control': 0.0}])
        run3, _action = self.generate()
        self.assertEqual(sorted(run3.line_ids.mapped('category')), ['payment', 'payment'])

    def test_manual_match_only_within_a_pair(self):
        """P8: no se emparejan líneas de pares distintos."""
        company_c = self.setup_other_company(name='Equipamiento (test)')
        company_c['company'].vat = '20612507083'
        self.config.company_ids = [Command.link(company_c['company'].id)]
        self.payment_entry(self.company_data, self.partner_b_in_a, self.company_data['default_account_receivable'], -1000.0)
        self.payment_entry(company_c, self.partner_a_in_b, company_c['default_account_payable'], 1000.0)
        run, _action = self.generate()
        lines = run.line_ids
        self.assertEqual(len(lines), 2)
        with self.assertRaisesRegex(UserError, 'no son contraparte entre sí'):
            lines.action_manual_match()
        with self.assertRaisesRegex(UserError, 'no son contraparte entre sí'):
            self.env['ic.reconciliation.match.wizard'].create(
                {'line_ids': lines.ids, 'reason': 'other', 'reason_note': 'prueba pares distintos'}).action_confirm()

    def test_cron_without_companies_or_responsible(self):
        """P1: sin empresas en la configuración usa todas las que tienen RUC, y avisa que falta el responsable."""
        self.config.write({'company_ids': [Command.clear()], 'responsible_user_id': False})
        self.payment_entry(self.company_data, self.partner_b_in_a, self.company_data['default_account_receivable'], 100.0)
        with self.assertLogs(
            'odoo.addons.empiria_intercompany_reconciliation.models.ic_reconciliation_run',
            level='WARNING',
        ) as warnings:
            run = self.env['ic.reconciliation.run']._cron_generate()
        self.assertEqual(len(warnings.output), 2)
        self.assertIn('no tiene empresas elegidas', warnings.output[0])
        self.assertIn('no tiene responsable', warnings.output[1])
        self.assertEqual(run.state, 'done')
        self.assertTrue(run.control_ok)
        self.assertLessEqual(self.company_a | self.company_b, run.company_ids)
        self.assertEqual(run.pending_line_count, 1)
        messages = ' '.join(run.message_ids.mapped('body'))
        self.assertIn('no tiene empresas elegidas', messages)
        self.assertIn('no tiene responsable', messages)

    def test_export_xlsx(self):
        self.sale(500.0, 'F001-00000020')
        run, _action = self.generate()
        action = run.action_export_xlsx()
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        self.assertTrue(attachment.name.startswith('Conciliacion_Intercompany_documentos_'))
        content = base64.b64decode(attachment.datas)
        sheets = zipfile.ZipFile(io.BytesIO(content)).read('xl/workbook.xml').decode()
        for name in ('Notas', 'Resumen', 'Por categoría', 'Detalle', 'Emparejamientos manuales', 'Reglas'):
            self.assertIn(f'name="{name}"', sheets)

    def test_daily_cron_notifies_the_responsible(self):
        self.payment_entry(self.company_data, self.partner_b_in_a, self.company_data['default_account_receivable'], 100.0)
        self.env['ic.reconciliation.run']._cron_generate()
        first = self.env['ic.reconciliation.run'].search([('origin', '=', 'cron')], limit=1)
        self.assertEqual(first.date_from, date(self.today.year, 1, 1), 'Por defecto, año en curso')
        self.assertFalse(first.activity_ids, 'Sin ejecución anterior no hay pendientes "nuevos"')
        self.payment_entry(self.company_data, self.partner_b_in_a, self.company_data['default_account_receivable'], 55.0)
        self.env['ic.reconciliation.run']._cron_generate()
        second = self.env['ic.reconciliation.run'].search([('origin', '=', 'cron')], limit=1)
        self.assertEqual(second.new_line_count, 1)
        self.assertEqual(second.activity_ids.user_id, self.env.user)

    def test_details_only_for_allowed_companies(self):
        self.payment_entry(self.company_data, self.partner_b_in_a, self.company_data['default_account_receivable'], 100.0)
        self.payment_entry(self.company_b_data, self.partner_a_in_b, self.company_b_data['default_account_payable'], 30.0)
        run, _action = self.generate()
        user = new_test_user(self.env, 'ic_user_b', groups='account.group_account_user',
                             company_id=self.company_b.id, company_ids=[self.company_b.id])
        lines = self.env['ic.reconciliation.line'].with_user(user).search([('run_id', '=', run.id)])
        self.assertEqual(lines.company_id, self.company_b)
        self.assertEqual(len(self.env['ic.reconciliation.pair'].with_user(user).search([('run_id', '=', run.id)])), 1,
                         'Los totales del par sí se ven')
        with self.assertRaisesRegex(UserError, 'Responsable'):
            lines.with_user(user).action_mark_reviewed()

    def test_period_from_to(self):
        """Generar con periodo: año o desde - hasta; filtros de fecha y Excel."""
        self.payment_entry(self.company_data, self.partner_b_in_a, self.company_data['default_account_receivable'], 70.0,
                           date=self.today - timedelta(days=400))
        new = self.payment_entry(self.company_data, self.partner_b_in_a, self.company_data['default_account_receivable'], 30.0)
        date_from = self.today.replace(day=1)

        run, _action = self.generate(period='range', date_from=date_from)
        self.assertEqual(run.date_from, date_from)
        self.assertIn(f"del {date_from:%d/%m/%Y} al {self.today:%d/%m/%Y}", run.name)
        self.assertRecordValues(run.pair_ids, [{
            'difference': 100.0, 'opening_difference': 70.0, 'amount_prior_period': 70.0,
            'amount_payment': 30.0, 'control': 0.0, 'pending_count': 1, 'date_from': date_from, 'is_last': True,
        }])
        prior = run.line_ids.filtered(lambda line: line.category == 'prior_period')
        self.assertRecordValues(prior, [{'effect_pen': 70.0, 'status': 'matched', 'date': date_from - timedelta(days=1)}])
        self.assertEqual(run.line_ids.filtered(lambda line: line.category == 'payment').move_id, new)
        # Filtros de las vistas: última ejecución y fecha del documento.
        Line = self.env['ic.reconciliation.line']
        self.assertEqual(Line.search([('is_last', '=', True), ('date', '>=', date_from)]).move_id, new)

        run_year, _action = self.generate(period='year', year=str(self.today.year))
        self.assertEqual(run_year.date_from, date(self.today.year, 1, 1))
        self.assertEqual(run_year.date_to, self.today)
        self.assertFalse(run.is_last)
        self.assertEqual(self.env['ic.reconciliation.pair'].search([('is_last', '=', True)]).run_id, run_year)

        run_all, _action = self.generate(period='all', date_from=date_from)
        self.assertFalse(run_all.date_from, 'Acumulado: sin fecha desde')
        self.assertEqual(sorted(run_all.line_ids.mapped('effect_pen')), [30.0, 70.0])

        action = run.action_export_xlsx()
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        self.assertIn(f"{date_from:%d-%m-%Y}_al_{self.today:%d-%m-%Y}", attachment.name)

        with self.assertRaisesRegex(UserError, 'no puede ser posterior'):
            self.env['ic.reconciliation.generate'].create({
                'period': 'range', 'date_from': self.today + timedelta(days=1), 'date_to': self.today}).action_generate()
        with self.assertRaises(ValidationError):
            run.write({'date_from': self.today + timedelta(days=1)})

    def test_cron_period_options(self):
        Run = self.env['ic.reconciliation.run']
        self.config.write({'cron_period': 'months', 'cron_months': 6})
        Run._cron_generate()
        self.assertEqual(Run.search([], limit=1).date_from, self.today + relativedelta(months=-6, days=1))
        self.config.write({'cron_period': 'all'})
        Run._cron_generate()
        self.assertFalse(Run.search([], limit=1).date_from)
        with self.assertRaises(ValidationError):
            self.config.write({'cron_period': 'fixed', 'cron_date_from': False})

    def test_period_shortcuts(self):
        Wizard = self.env['ic.reconciliation.generate']
        self.assertEqual(Wizard.create({'period': 'current_month'})._period_dates(), (self.today.replace(day=1), self.today))
        self.assertEqual(Wizard.create({'period': 'last_12'})._period_dates(),
                         (self.today + relativedelta(months=-12, days=1), self.today))
        self.assertEqual(Wizard.create({})._period_dates(), (date(self.today.year, 1, 1), self.today),
                         'Por defecto, año en curso')

    def test_other_account_family_in_odoo(self):
        """N2 en Odoo: A cobra en 12 y B lo registra en una 46: conciliado con observación, no pendiente."""
        loan_account = self.env['account.account'].with_company(self.company_b).create({
            'code': '469901', 'name': 'Préstamos de terceros', 'account_type': 'liability_current',
            'reconcile': True,
        })
        self.config.write({'payable_prefixes': f'{self.config.payable_prefixes},4699'})
        self.payment_entry(self.company_data, self.partner_b_in_a, self.company_data['default_account_receivable'], 500.0)
        self.payment_entry(self.company_b_data, self.partner_a_in_b, loan_account, -500.0)
        run, _action = self.generate(include_balanced=True)
        line = run.line_ids
        self.assertRecordValues(line, [{'category': 'matched_account', 'status': 'matched', 'is_pending': False}])
        self.assertIn('469901', line.account_note)
        self.assertEqual(run.pending_line_count, 0)
        self.assertEqual(self.env['ic.reconciliation.line'].search_count(
            [('run_id', '=', run.id), ('account_note', '!=', False)]), 1, 'Filtro Conciliado – cuenta distinta')
