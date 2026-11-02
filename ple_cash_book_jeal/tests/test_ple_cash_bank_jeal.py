import base64

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

PERIOD_DATE = '2026-09-15'


@tagged('post_install', '-at_install')
class TestPleCashBankJeal(AccountTestInvoicingCommon):

    @classmethod
    def setup_independent_company(cls, **kwargs):
        # A chart creates journals; respect optional customer access restrictions.
        group = cls.env.ref('restrict_journal_creation.group_allow_create_account_journal', raise_if_not_found=False)
        if group:
            cls.env.user.write({'groups_id': [(4, group.id)]})
        return super().setup_independent_company(**kwargs)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.company.write({'vat': '20552711867', 'ple_type_contributor': 'CUO'})
        cls.means = {
            code: cls.env['payment.methods.codes'].search([('code', '=', code)], limit=1)
            or cls.env['payment.methods.codes'].create({'code': code, 'description': code})
            for code in ('001', '003', '007')
        }
        bcp = cls.env['res.bank'].create({'name': 'BCP', 'sunat_bank_code': '02'})
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.bank_journal.write({
            'bank_account_id': cls.env['res.partner.bank'].create({
                'acc_number': '205-9292910-0-82', 'bank_id': bcp.id, 'partner_id': cls.company.partner_id.id,
            }).id,
            'l10n_pe_payment_means_id': cls.means['003'].id,
        })
        cls.bank_account = cls.bank_journal.default_account_id
        cls.bank_account.ple_selection = 'bank'
        cls.cash_journal = cls.company_data['default_journal_cash']
        cls.cash_account = cls.cash_journal.default_account_id
        cls.cash_account.ple_selection = 'cash'
        cls.misc_journal = cls.company_data['default_journal_misc']
        # Como en producción: correlativo «M» + n° de línea (ple_sale_book).
        (cls.bank_journal | cls.cash_journal | cls.misc_journal | cls.company_data['default_journal_sale']).ple_journal_correlative = 'M'
        cls.ruc_partner = cls.env['res.partner'].create({
            'name': 'TRAFIGURA PERU S.A.C.',
            'vat': '20514298451',
            'l10n_latam_identification_type_id': cls.env.ref('l10n_pe.it_RUC').id,
        })

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def create_entry(self, lines, journal=None, partner=None, ref=None):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': PERIOD_DATE,
            'journal_id': (journal or self.misc_journal).id,
            'partner_id': partner and partner.id,
            'ref': ref,
            'line_ids': [Command.create({
                'name': name, 'account_id': account.id, 'debit': debit, 'credit': credit,
                'partner_id': line_partner and line_partner.id,
            }) for account, debit, credit, name, line_partner in lines],
        })
        move.action_post()
        return move

    def create_statement_line(self, amount, journal=None, **values):
        return self.env['account.bank.statement.line'].create({
            'journal_id': (journal or self.bank_journal).id,
            'date': PERIOD_DATE,
            'payment_ref': 'TRANSFERENCIA CCE',
            'amount': amount,
            **values,
        })

    def generate(self):
        report = self.env['ple.report.cash.bank'].create({
            'company_id': self.company.id,
            'date_start': '2026-09-01',
            'date_end': '2026-09-30',
            'state_send': '1',
        })
        report.action_generate_excel()
        # El correlativo se escribe con SQL: se releen los apuntes para comparar.
        self.env.invalidate_all()
        return report

    @staticmethod
    def rows(report, register):
        txt = base64.b64decode(report[f'txt_binary_{register}']).decode()
        return [line.split('|') for line in txt.split('\r\n') if line.strip()]

    # -------------------------------------------------------------------------
    # D1 / C1: el 1.2 solo lleva cuentas de bancos
    # -------------------------------------------------------------------------

    def test_bank_register_takes_bank_and_account_number_from_journal(self):
        statement_line = self.create_statement_line(1529.45, partner_id=self.ruc_partner.id, ref='OP 000413')

        rows = self.rows(self.generate(), 'bank')

        self.assertEqual(len(rows), 1, 'Solo la línea del banco: la contrapartida (cuenta de suspenso) no va')
        row = rows[0]
        bank_line = statement_line.move_id.line_ids.filtered(lambda l: l.account_id == self.bank_account)
        self.assertEqual(row[:6], [
            '20260900', statement_line.move_id.name.replace('/', ''), bank_line.ple_correlative or 'M000000001',
            '02', '205-9292910-0-82', '15/09/2026',
        ])
        self.assertEqual(row[6], '003')
        self.assertEqual(row[7], 'TRANSFERENCIA CCE')
        self.assertEqual(row[8:11], ['6', '20514298451', 'TRAFIGURA PERU S.A.C.'])
        self.assertEqual(row[11], 'OP000413')
        self.assertEqual(row[12:15], ['1529.45', '0.00', '1'])

    def test_bank_account_without_bank_blocks_the_report(self):
        transit = self.env['account.account'].create({
            'code': '104101', 'name': 'Cuenta transitoria', 'account_type': 'asset_current', 'ple_selection': 'bank',
        })
        self.create_entry([
            (transit, 100.0, 0.0, 'Transferencia', None),
            (self.company_data['default_account_revenue'], 0.0, 100.0, 'Transferencia', None),
        ])
        with self.assertRaisesRegex(UserError, '104101 Cuenta transitoria tiene PLE = 1.2 pero no es la cuenta de ningún diario de banco'):
            self.generate()

    def test_bank_without_sunat_code_blocks_the_report(self):
        self.bank_journal.bank_account_id.bank_id.sunat_bank_code = False
        self.create_statement_line(100.0)
        with self.assertRaisesRegex(UserError, 'código SUNAT'):
            self.generate()

    def test_accounts_without_movements_do_not_block(self):
        self.env['account.account'].create({
            'code': '104102', 'name': 'Transitoria sin movimientos', 'account_type': 'asset_current', 'ple_selection': 'bank',
        })
        self.create_statement_line(100.0)
        self.assertEqual(len(self.rows(self.generate(), 'bank')), 1)

    def test_bank_register_totals_match_the_ledger(self):
        self.create_statement_line(1601.39)
        self.create_statement_line(-558.01)
        self.create_entry([
            (self.cash_account, 20000.0, 0.0, 'INGRESO DE EFECTIVO DEL CHEQUE 00000414', None),
            (self.bank_account, 0.0, 20000.0, 'CHEQUE 00000414', None),
        ], journal=self.bank_journal)
        rows = self.rows(self.generate(), 'bank')
        ledger = self.env['account.move.line'].search([('account_id', '=', self.bank_account.id), ('parent_state', '=', 'posted')])
        self.assertAlmostEqual(sum(float(row[12]) for row in rows), sum(ledger.mapped('debit')))
        self.assertAlmostEqual(sum(float(row[13]) for row in rows), sum(ledger.mapped('credit')))

    # -------------------------------------------------------------------------
    # D2: 1.1 Efectivo
    # -------------------------------------------------------------------------

    def test_cash_register_is_generated(self):
        move = self.create_entry([
            (self.cash_account, 40000.0, 0.0, 'INGRESO DE EFECTIVO DEL CHEQUE 00000414', None),
            (self.bank_account, 0.0, 40000.0, 'CHEQUE 00000414', None),
        ], journal=self.bank_journal, ref='CHQ 414')

        report = self.generate()
        cash_rows = self.rows(report, 'cash')

        self.assertEqual(len(cash_rows), 1)
        row = cash_rows[0]
        cash_line = move.line_ids.filtered(lambda l: l.account_id == self.cash_account)
        self.assertEqual(row[0:4], [
            '20260900', move.name.replace('/', ''), cash_line.ple_correlative or 'M000000001',
            self.cash_account.code.replace('.', ''),
        ])
        self.assertEqual(row[6], self.company.currency_id.name)
        self.assertEqual(row[7], '00', 'Sin comprobante relacionado')
        self.assertEqual(row[9], move.name.replace('/', '')[:20], 'Sin documento: número = asiento')
        self.assertEqual(row[10], '15/09/2026')
        self.assertEqual(row[13], 'INGRESO DE EFECTIVO DEL CHEQUE 00000414')
        self.assertEqual(row[14], 'CHQ 414')
        self.assertEqual(row[15:17], ['40000.00', '0.00'])
        self.assertEqual(row[18], '1')
        self.assertTrue(report.txt_filename_cash.endswith('01111.txt'), 'Indicador «con contenido»')
        self.assertTrue(report.txt_filename_bank.endswith('01111.txt'))

    def create_vendor_bill(self, number, amount=1000.0):
        bill = self.init_invoice('in_invoice', partner=self.ruc_partner, amounts=[amount], invoice_date=PERIOD_DATE)
        bill.ref = number
        if 'l10n_latam_document_type_id' in bill._fields:
            bill.l10n_latam_document_type_id = self.env.ref('l10n_pe.document_type01')
        bill.action_post()
        return bill

    def pay_in_cash(self, invoice):
        counterpart = invoice.line_ids.filtered(lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable'))
        payment = self.create_entry([
            (self.cash_account, max(counterpart.balance, 0.0), max(-counterpart.balance, 0.0), 'Pago en efectivo', None),
            (counterpart.account_id, max(-counterpart.balance, 0.0), max(counterpart.balance, 0.0), 'Pago en efectivo', self.ruc_partner),
        ], journal=self.cash_journal)
        (payment.line_ids.filtered(lambda l: l.account_id == counterpart.account_id) + counterpart).reconcile()
        return payment

    def test_cash_paid_bill_reports_its_own_document(self):
        self.pay_in_cash(self.create_vendor_bill('E001-00000108'))
        row = self.rows(self.generate(), 'cash')[0]
        self.assertEqual(row[7:10], ['01', 'E001', '00000108'])

    def test_document_of_another_line_is_not_carried_over(self):
        """Revisión 03/10, error 2: Sinetics (invoice_type_document) copia al conciliar
        el comprobante a todas las líneas del extracto; el 1.1 no debe tomarlo."""
        self.pay_in_cash(self.create_vendor_bill('E001-00000108'))
        unrelated = self.create_entry([
            (self.cash_account, 0.0, 250.0, 'PAGOS AFP PROFUTUR', None),
            (self.company_data['default_account_expense'], 250.0, 0.0, 'PAGOS AFP PROFUTUR', None),
        ], journal=self.cash_journal)
        values = {'serie_correlative': 'E001-00000108'}
        if 'l10n_latam_document_type_id' in unrelated.line_ids._fields:
            values['l10n_latam_document_type_id'] = self.env.ref('l10n_pe.document_type01').id
        unrelated.line_ids.write(values)

        rows = {row[1]: row for row in self.rows(self.generate(), 'cash')}

        cuo = unrelated.name.replace('/', '')
        self.assertEqual(rows[cuo][7:10], ['00', '', cuo[:20]])
        self.assertEqual([row[7:10] for row in rows.values()].count(['01', 'E001', '00000108']), 1)

    def test_cash_paid_invoice_reports_document_and_structured_data(self):
        invoice = self.init_invoice('out_invoice', partner=self.ruc_partner, amounts=[1000.0], post=True)
        receivable = invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        self.pay_in_cash(invoice)

        row = self.rows(self.generate(), 'cash')[0]

        self.assertEqual(row[17], '&'.join((
            '140100', invoice.date.strftime('%Y%m00'), invoice.name.replace('/', '').replace(' ', ''),
            receivable.ple_correlative or 'M000000001',
        )))
        self.assertEqual(row[12], invoice.invoice_date.strftime('%d/%m/%Y'), 'Fecha de operación del comprobante')

    # -------------------------------------------------------------------------
    # D3: medio de pago
    # -------------------------------------------------------------------------

    def test_payment_means_show_and_search_their_code(self):
        means = self.means['007']
        self.assertTrue(means.display_name.startswith('007 - '))
        self.assertIn(means, self.env['payment.methods.codes'].search([('display_name', 'ilike', '007')]))

    def test_statement_line_takes_payment_means_from_journal(self):
        statement_line = self.create_statement_line(100.0)
        self.assertEqual(statement_line.move_id.payment_method_id, self.means['003'])
        statement_line.payment_method_id = self.means['001']
        self.assertEqual(self.rows(self.generate(), 'bank')[0][6], '001', 'El usuario puede cambiarlo')

    def test_cheque_payment_means_comes_from_payment_method(self):
        outbound = self.bank_journal.outbound_payment_method_line_ids[:1]
        outbound.l10n_pe_payment_means_id = self.means['007']
        outstanding = self.env['account.account'].create({
            'code': '104199', 'name': 'Pagos pendientes', 'account_type': 'asset_current', 'reconcile': True,
        })
        outbound.payment_account_id = outstanding
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound', 'partner_type': 'supplier', 'partner_id': self.ruc_partner.id,
            'amount': 20000.0, 'date': PERIOD_DATE, 'journal_id': self.bank_journal.id,
            'payment_method_line_id': outbound.id,
        })
        payment.action_post()

        self.assertEqual(payment.means_payment_id, self.means['007'])
        self.assertEqual(payment.move_id.payment_method_id, self.means['007'])
        payment.means_payment_id = self.means['003']
        self.assertEqual(payment.move_id.payment_method_id, self.means['003'], 'El asiento sigue al pago')

    def test_missing_payment_means_defaults_to_003_and_is_warned(self):
        """Revisión 03/10: el campo 7 es obligatorio, nunca vacío."""
        self.bank_journal.l10n_pe_payment_means_id = False
        statement_line = self.create_statement_line(100.0)

        report = self.generate()

        self.assertEqual(self.rows(report, 'bank')[0][6], '003')
        self.assertEqual(report.l10n_pe_missing_means_move_ids, statement_line.move_id)
        self.assertIn('1 movimiento(s) bancario(s) sin medio de pago (tabla 1): se informaron con 003', report.error_dialog)

        action = report.action_l10n_pe_view_missing_means()
        self.assertEqual(self.env['account.move'].search(action['domain']), statement_line.move_id)
        statement_line.move_id.payment_method_id = self.means['001']
        report.action_rollback()
        self.assertFalse(report.l10n_pe_missing_means_move_ids)
        report.action_generate_excel()
        self.assertEqual(self.rows(report, 'bank')[0][6], '001')
        self.assertFalse(report.l10n_pe_missing_means_move_ids)

    def test_no_bank_line_has_an_empty_payment_means(self):
        self.bank_journal.l10n_pe_payment_means_id = False
        self.create_statement_line(100.0)
        self.create_statement_line(-30.0, payment_ref='IMPUESTO ITF')
        self.create_entry([
            (self.bank_account, 0.0, 80.0, 'Ajuste', None),
            (self.company_data['default_account_expense'], 80.0, 0.0, 'Ajuste', None),
        ], journal=self.bank_journal)
        self.assertTrue(all(row[6] for row in self.rows(self.generate(), 'bank')))

    def test_cheque_without_payment_means_is_007(self):
        """Como BCPS/2026/02265: asiento sin medio de pago, el diario propone 003."""
        self.create_entry([
            (self.cash_account, 40000.0, 0.0, 'INGRESO DE EFECTIVO DEL CHEQUE 00000414', None),
            (self.bank_account, 0.0, 40000.0, 'INGRESO DE EFECTIVO DEL CHEQUE 00000414', None),
        ], journal=self.bank_journal)
        report = self.generate()
        self.assertEqual(self.rows(report, 'bank')[0][6], '007')
        self.assertFalse(report.l10n_pe_missing_means_move_ids)

    def test_statement_line_takes_payment_means_from_operation(self):
        cheque = self.create_statement_line(-500.0, payment_ref='CHEQUE 00000415 PROVEEDOR')
        deposit = self.create_statement_line(800.0, payment_ref='DEPOSITO EN EFECTIVO')
        transfer = self.create_statement_line(900.0, payment_ref='TRANFERENCIA CCE')
        self.assertEqual(cheque.move_id.payment_method_id, self.means['007'])
        self.assertEqual(deposit.move_id.payment_method_id, self.means['001'])
        self.assertEqual(transfer.move_id.payment_method_id, self.means['003'], 'El del diario')

    def test_a_move_with_several_bank_lines_is_listed_once(self):
        self.bank_journal.l10n_pe_payment_means_id = False
        self.create_entry([
            (self.bank_account, 100.0, 0.0, 'Ajuste 1', None),
            (self.bank_account, 50.0, 0.0, 'Ajuste 2', None),
            (self.company_data['default_account_revenue'], 0.0, 150.0, 'Ajuste', None),
        ], journal=self.bank_journal)
        report = self.generate()
        self.assertEqual(len(report.l10n_pe_missing_means_move_ids), 1)
        self.assertIn('1 movimiento(s)', report.error_dialog)

    # -------------------------------------------------------------------------
    # D4: girador / beneficiario
    # -------------------------------------------------------------------------

    def test_drawer_from_the_only_counterpart_partner(self):
        self.create_entry([
            (self.bank_account, 0.0, 300.0, 'Pago', None),
            (self.company_data['default_account_payable'], 300.0, 0.0, 'Pago', self.ruc_partner),
        ], journal=self.bank_journal)
        self.assertEqual(self.rows(self.generate(), 'bank')[0][8:11], ['6', '20514298451', 'TRAFIGURA PERU S.A.C.'])

    def test_bank_charges_without_partner_are_various(self):
        self.create_statement_line(-0.05, payment_ref='IMPUESTO ITF')
        self.assertEqual(self.rows(self.generate(), 'bank')[0][8:11], ['-', '-', 'VARIOS'])

    def test_several_counterpart_partners_are_various(self):
        other = self.env['res.partner'].create({'name': 'Otro cliente'})
        self.create_entry([
            (self.bank_account, 300.0, 0.0, 'Depósitos', None),
            (self.company_data['default_account_receivable'], 0.0, 200.0, 'Depósito', self.ruc_partner),
            (self.company_data['default_account_receivable'], 0.0, 100.0, 'Depósito', other),
        ], journal=self.bank_journal)
        self.assertEqual(self.rows(self.generate(), 'bank')[0][8:11], ['-', '-', 'VARIOS'])

    def test_partner_without_document_is_warned(self):
        no_vat = self.env['res.partner'].create({'name': 'BALAREZO LAM ALDO ENRIQUE'})
        statement_line = self.create_statement_line(-250.0, partner_id=no_vat.id)

        report = self.generate()

        self.assertEqual(self.rows(report, 'bank')[0][8:11], ['-', '-', 'BALAREZO LAM ALDO ENRIQUE'])
        self.assertEqual(report.l10n_pe_undocumented_partner_ids, no_vat)
        self.assertIn('1 socio(s) sin tipo o número de documento', report.error_dialog)
        action = report.action_l10n_pe_view_undocumented_partners()
        self.assertEqual(self.env['res.partner'].search(action['domain']), no_vat)

    # -------------------------------------------------------------------------
    # D5: CUO y correlativo por línea, iguales al Libro Diario 5.1
    # -------------------------------------------------------------------------

    def test_each_line_keeps_its_own_correlative(self):
        """Transferencia entre dos bancos: dos líneas del mismo asiento en el 1.2
        con correlativos distintos (los de cada línea, como en el 5.1)."""
        other_journal = self.company_data['default_journal_bank'].copy({'name': 'BCP ME', 'code': 'BCPD'})
        other_journal.write({
            'bank_account_id': self.env['res.partner.bank'].create({
                'acc_number': '205-8744684-1-56', 'bank_id': self.bank_journal.bank_account_id.bank_id.id,
                'partner_id': self.company.partner_id.id,
            }).id,
        })
        other_journal.default_account_id.ple_selection = 'bank'
        move = self.create_entry([
            (self.bank_account, 0.0, 500.0, 'Transferencia', None),
            (other_journal.default_account_id, 500.0, 0.0, 'Transferencia', None),
        ])

        report = self.generate()
        rows = self.rows(report, 'bank')

        correlatives = [row[2] for row in rows]
        self.assertEqual(sorted(correlatives), sorted(line.ple_correlative for line in move.line_ids))
        self.assertEqual(len(set(correlatives)), 2)
        self.assertNotIn('repetido', report.error_dialog or '')
