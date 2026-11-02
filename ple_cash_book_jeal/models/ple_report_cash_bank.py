import base64
import re
from collections import Counter

from odoo import Command, _, fields, models
from odoo.exceptions import UserError

from odoo.addons.ple_cash_book.reports.report_ple_bank import BankReport
from odoo.addons.ple_cash_book.reports.report_ple_cash import CashReport

# Longitudes máximas de la estructura SUNAT (Libro Caja y Bancos 1.1 / 1.2).
GLOSS_MAX_LENGTH = 200
OPERATION_DESCRIPTION_MAX_LENGTH = 100
TRANSACTION_NUMBER_MAX_LENGTH = 20
NO_PARTNER = ('-', '-', 'VARIOS')
DEFAULT_PAYMENT_MEANS_CODE = '003'


def _clean_text(value, max_length):
    """Texto de un campo del TXT: sin el separador «|» ni saltos de línea."""
    return re.sub(r'[|\r\n]+', ' ', value or '').strip()[:max_length]


def _format_amount(amount):
    return f'{amount:.2f}'


def _format_date(date):
    return date.strftime('%d/%m/%Y') if date else ''


class PleReportCashBank(models.Model):
    _inherit = 'ple.report.cash.bank'

    l10n_pe_missing_means_move_ids = fields.Many2many(
        comodel_name='account.move',
        relation='ple_report_cash_bank_missing_means_move_rel',
        string='Movimientos sin medio de pago',
        readonly=True,
        copy=False,
    )
    l10n_pe_missing_means_count = fields.Integer(compute='_compute_l10n_pe_observation_counts')
    l10n_pe_undocumented_partner_ids = fields.Many2many(
        comodel_name='res.partner',
        relation='ple_report_cash_bank_undocumented_partner_rel',
        string='Socios sin documento',
        readonly=True,
        copy=False,
    )
    l10n_pe_undocumented_partner_count = fields.Integer(compute='_compute_l10n_pe_observation_counts')

    def _compute_l10n_pe_observation_counts(self):
        for report in self:
            report.l10n_pe_missing_means_count = len(report.l10n_pe_missing_means_move_ids)
            report.l10n_pe_undocumented_partner_count = len(report.l10n_pe_undocumented_partner_ids)

    def action_l10n_pe_view_missing_means(self):
        """Lista editable (también en bloque) para asignar el medio de pago."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Movimientos sin medio de pago'),
            'res_model': 'account.move',
            'view_mode': 'list',
            'views': [(self.env.ref('ple_cash_book_jeal.view_move_list_payment_means').id, 'list')],
            'domain': [('id', 'in', self.l10n_pe_missing_means_move_ids.ids)],
            'context': {'create': False, 'delete': False},
        }

    def action_l10n_pe_view_undocumented_partners(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Socios sin documento'),
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.l10n_pe_undocumented_partner_ids.ids)],
            'context': {'create': False},
        }

    def action_rollback(self):
        res = super().action_rollback()
        self.write({'l10n_pe_missing_means_move_ids': [Command.clear()], 'l10n_pe_undocumented_partner_ids': [Command.clear()]})
        return res

    def action_generate_excel(self):
        for report in self:
            report._l10n_pe_generate()

    def _l10n_pe_generate(self):
        self.ensure_one()
        lines = self._l10n_pe_get_period_lines()
        cash_lines = lines.filtered(lambda line: line.account_id.ple_selection == 'cash')
        bank_lines = lines - cash_lines
        bank_accounts = self._l10n_pe_get_bank_accounts(bank_lines.account_id)

        observations = {'missing_means': self.env['account.move'], 'undocumented': self.env['res.partner']}
        cash_values = [self._l10n_pe_prepare_cash_values(line) for line in cash_lines]
        bank_values = [self._l10n_pe_prepare_bank_values(line, bank_accounts[line.account_id], observations)
                       for line in bank_lines]
        warnings = self._l10n_pe_summarize_observations(observations)
        warnings += self._l10n_pe_check_unique_keys(cash_values, _('1.1 Efectivo'))
        warnings += self._l10n_pe_check_unique_keys(bank_values, _('1.2 Cuentas corrientes'))
        self._l10n_pe_write_reports(cash_values, bank_values, warnings)
        self.write({
            'l10n_pe_missing_means_move_ids': [Command.set(observations['missing_means'].ids)],
            'l10n_pe_undocumented_partner_ids': [Command.set(observations['undocumented'].ids)],
        })

    # -------------------------------------------------------------------------
    # Selección de líneas
    # -------------------------------------------------------------------------

    def _l10n_pe_get_period_lines(self):
        """Apuntes publicados del periodo en las cuentas marcadas 1.1 o 1.2."""
        self.ensure_one()
        # ple_sale_book escribe el correlativo con SQL directo: se relee de la base.
        self.env['account.move.line'].invalidate_model(['ple_correlative'])
        return self.env['account.move.line'].with_company(self.company_id).search([
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_start),
            ('date', '<=', self.date_end),
            ('account_id.ple_selection', 'in', ('cash', 'bank')),
            '|',
            ('account_id.company_ids', 'in', self.company_id.ids),
            ('account_id.company_ids', '=', False),
        ], order='date, move_name, id')

    def _l10n_pe_get_bank_accounts(self, accounts):
        """Cuenta bancaria de cada cuenta contable del 1.2: la del diario de banco
        que la usa como cuenta por defecto (o la configurada en la cuenta).

        El 1.2 solo admite cuentas de bancos: si una cuenta marcada 1.2 con
        movimientos no tiene banco, el libro no se genera.
        """
        self.ensure_one()
        journals = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'bank'),
            ('default_account_id', 'in', accounts.ids),
            ('bank_account_id', '!=', False),
        ])
        bank_accounts = {}
        problems = []
        for account in accounts.sorted('code'):
            bank_account = journals.filtered(lambda j: j.default_account_id == account)[:1].bank_account_id or account.bank_id
            if not bank_account.acc_number:
                problems.append(_(
                    'La cuenta %s tiene PLE = 1.2 pero no es la cuenta de ningún diario de banco con cuenta '
                    'bancaria.', account.display_name,
                ))
            elif not bank_account.bank_id.sunat_bank_code:
                problems.append(_(
                    'La cuenta bancaria %(bank_account)s de la cuenta %(account)s no tiene el código SUNAT '
                    'de la entidad financiera.', bank_account=bank_account.display_name, account=account.display_name,
                ))
            bank_accounts[account] = bank_account
        if problems:
            raise UserError(_(
                'No se generó el Libro Caja y Bancos:\n%(problems)s\n\nEl 1.2 solo admite cuentas de bancos, porque '
                'informa el banco y el número de cuenta. En Contabilidad › Configuración › Plan contable, campo «PLE»:\n'
                '- Caja, efectivo, fondos fijos y cuentas transitorias o de transferencias: 1.1.\n'
                '- Cuenta de un banco: 1.2, y en su diario de banco registre la cuenta bancaria (con su banco).',
                problems='\n'.join(f'- {problem}' for problem in problems),
            ))
        return bank_accounts

    # -------------------------------------------------------------------------
    # Campos comunes
    # -------------------------------------------------------------------------

    def _l10n_pe_get_cuo(self, move):
        """CUO como en el Libro Diario 5.1: nombre del asiento sin «/», «-» ni espacios."""
        return re.sub(r'[/\- ]', '', move.name or '')

    def _l10n_pe_get_correlative(self, line):
        """Correlativo de la línea, el mismo que informa el Libro Diario 5.1
        (función get_journal_correlative de ple_diary_book)."""
        contributor = self.company_id.ple_type_contributor
        if contributor == 'CUO':
            return line.ple_correlative or 'M000000001'
        if contributor == 'RER':
            return 'M-RER'
        return ''

    def _l10n_pe_common_values(self, line):
        return {
            'period': line.date.strftime('%Y%m00'),
            'cuo': self._l10n_pe_get_cuo(line.move_id),
            'correlative': self._l10n_pe_get_correlative(line),
            'debit': _format_amount(line.debit),
            'credit': _format_amount(line.credit),
            'state': 1,
        }

    # -------------------------------------------------------------------------
    # 1.1 Detalle de los movimientos del efectivo
    # -------------------------------------------------------------------------

    def _l10n_pe_prepare_cash_values(self, line):
        move = line.move_id
        # Campos 8 a 10 solo desde el comprobante del propio asiento. No se usan
        # l10n_latam_document_type_id / serie_correlative de la línea: Sinetics
        # (invoice_type_document) los copia al conciliar a todas las líneas del
        # extracto, y el comprobante de un pago aparecía en operaciones ajenas.
        invoice = self._l10n_pe_get_related_invoice(line)
        series, number = self._l10n_pe_split_document_number(self._l10n_pe_get_invoice_number(invoice))
        document_type_code = invoice.l10n_latam_document_type_id.code if number else ''
        return {
            **self._l10n_pe_common_values(line),
            'account_code': re.sub(r'[/\-.]', '', line.account_id.code or ''),
            'unit_operation_code': '',
            'cost_center_code': self._l10n_pe_get_cost_center(line),
            'currency_name': line.currency_id.name,
            'type_payment_document': document_type_code or '00',
            'serie': series,
            'document_number': number or self._l10n_pe_get_cuo(move)[:TRANSACTION_NUMBER_MAX_LENGTH],
            'accounting_date': _format_date(move.date),
            'date_due': _format_date(line.date_maturity),
            'operation_date': _format_date(invoice.invoice_date or move.invoice_date or move.date),
            'gloss': _clean_text(line.name or move.ref or move.name, GLOSS_MAX_LENGTH),
            'referential_gloss': _clean_text(move.ref, GLOSS_MAX_LENGTH),
            'data_structured': self._l10n_pe_get_structured_data(invoice),
        }

    def _l10n_pe_get_related_invoice(self, line):
        """Comprobante del Registro de Ventas/Compras del movimiento: el propio
        asiento si es un comprobante o el único comprobante conciliado con él,
        directamente o a través del pago que concilia la línea de extracto."""
        move = line.move_id
        if move.is_invoice(include_receipts=True):
            return move

        def is_invoice(m):
            return m.is_invoice(include_receipts=True)

        matched_moves = (move.line_ids._all_reconciled_lines().move_id - move)
        invoices = matched_moves.filtered(is_invoice)
        if not invoices:
            payment_moves = matched_moves.filtered('origin_payment_id')
            invoices = (payment_moves.line_ids._all_reconciled_lines().move_id - payment_moves).filtered(is_invoice)
        return invoices if len(invoices) == 1 else invoices.browse()

    @staticmethod
    def _l10n_pe_get_invoice_number(invoice):
        """Serie-número del comprobante (sin el prefijo del tipo de documento)."""
        if not invoice:
            return ''
        if invoice.journal_id.l10n_latam_use_documents and invoice.l10n_latam_document_number:
            return invoice.l10n_latam_document_number
        if invoice.is_purchase_document(include_receipts=True):
            return invoice.ref or invoice.serie_correlative
        return invoice.serie_correlative

    def _l10n_pe_get_structured_data(self, invoice):
        """Campo 18: «tabla&periodo&CUO&correlativo» del comprobante en el Registro
        de Ventas (140100) o de Compras (080100, 080200 no domiciliados)."""
        journal = invoice.journal_id
        if not invoice or journal.ple_no_include or journal.type not in ('sale', 'purchase'):
            return ''
        if journal.type == 'sale':
            register = '140100'
        else:
            register = '080200' if invoice.is_nodomicilied else '080100'
        term_line = invoice.line_ids.filtered(lambda l: l.display_type == 'payment_term')[:1] or invoice.line_ids[:1]
        return '&'.join((
            register,
            invoice.date.strftime('%Y%m00'),
            self._l10n_pe_get_cuo(invoice),
            self._l10n_pe_get_correlative(term_line),
        ))

    @staticmethod
    def _l10n_pe_split_document_number(reference):
        """«F001-00000123» → («F001», «00000123»)."""
        reference = (reference or '').replace(' ', '')
        if '-' not in reference:
            return '', reference[:TRANSACTION_NUMBER_MAX_LENGTH]
        series, number = reference.split('-', 1)
        return series[:4], number[:TRANSACTION_NUMBER_MAX_LENGTH]

    def _l10n_pe_get_cost_center(self, line):
        """Campo 6 (opcional): código de la cuenta analítica de la línea."""
        analytic_ids = [int(analytic_id) for key in (line.analytic_distribution or {}) for analytic_id in key.split(',')]
        return self.env['account.analytic.account'].browse(analytic_ids[:1]).code or ''

    # -------------------------------------------------------------------------
    # 1.2 Detalle de los movimientos de la cuenta corriente
    # -------------------------------------------------------------------------

    def _l10n_pe_prepare_bank_values(self, line, bank_account, observations):
        move = line.move_id
        statement_line = line.statement_line_id
        payment_means = self._l10n_pe_get_payment_means(line)
        if not payment_means:
            # El campo 7 es obligatorio: 003 y se lista para revisarlo.
            observations['missing_means'] |= move
            payment_means = self._l10n_pe_get_payment_means_by_code(DEFAULT_PAYMENT_MEANS_CODE)
        partner_values = self._l10n_pe_get_drawer_values(line, observations)
        transaction_number = move.ref or line.payment_id.payment_reference or move.name
        return {
            **self._l10n_pe_common_values(line),
            'bank_code': bank_account.bank_id.sunat_bank_code,
            'account_bank_code': bank_account.acc_number,
            'date': _format_date(line.date),
            'payment_method': payment_means.code or DEFAULT_PAYMENT_MEANS_CODE,
            'operation_description': _clean_text(
                statement_line.payment_ref or line.name or move.ref or move.name, OPERATION_DESCRIPTION_MAX_LENGTH,
            ),
            'partner_type_document': partner_values[0],
            'partner_document_number': partner_values[1],
            'partner_name': partner_values[2],
            'transaction_number': re.sub(r'[^a-zA-Z0-9]', '', transaction_number)[:TRANSACTION_NUMBER_MAX_LENGTH],
        }

    def _l10n_pe_get_payment_means(self, line):
        """Campo 7 (tabla 1): el del asiento (editable); si no tiene, el del pago,
        el de la operación bancaria (cheque 007, depósito 001) o el del diario."""
        move = line.move_id
        payment = line.payment_id
        means = move.payment_method_id or payment.means_payment_id
        if not means and payment:
            means = payment.journal_id._l10n_pe_get_payment_means(payment.payment_method_line_id)
        if not means:
            description = ' '.join(filter(None, [
                line.statement_line_id.payment_ref, move.ref, *move.line_ids.mapped('name'),
            ]))
            means = self.env['payment.methods.codes']._l10n_pe_from_description(description)
        return means or move.journal_id.l10n_pe_payment_means_id

    def _l10n_pe_get_payment_means_by_code(self, code):
        return self.env['payment.methods.codes']._l10n_pe_get_by_code(code)

    def _l10n_pe_get_drawer(self, line):
        """Girador o beneficiario: socio del asiento (o de la línea de extracto) o,
        si no hay, el de la contrapartida cuando es uno solo."""
        partner = line.move_id.partner_id or line.partner_id
        if not partner:
            counterpart_partners = (line.move_id.line_ids - line).partner_id
            if len(counterpart_partners) == 1:
                partner = counterpart_partners
        return partner.commercial_partner_id

    def _l10n_pe_get_drawer_values(self, line, observations):
        """Campos 9 a 11: tipo y número de documento (tabla 2) y nombre."""
        partner = self._l10n_pe_get_drawer(line)
        if not partner:
            return NO_PARTNER
        document_code = partner.l10n_latam_identification_type_id.l10n_pe_vat_code
        if not document_code or not partner.vat:
            observations['undocumented'] |= partner
            return ('-', '-', _clean_text(partner.name, 100))
        return (document_code, partner.vat, _clean_text(partner.name, 100))

    # -------------------------------------------------------------------------
    # Validaciones y archivos
    # -------------------------------------------------------------------------

    def _l10n_pe_summarize_observations(self, observations):
        messages = []
        if observations['missing_means']:
            messages.append(_(
                '%s movimiento(s) bancario(s) sin medio de pago (tabla 1): se informaron con 003 '
                '(transferencia de fondos). Revíselos con el botón «Sin medio de pago» y, si corresponde '
                'otro, cámbielo y vuelva a generar.', len(observations['missing_means']),
            ))
        if observations['undocumented']:
            messages.append(_(
                '%s socio(s) sin tipo o número de documento: los campos 9 y 10 quedan «-». '
                'Complételos con el botón «Socios sin documento».', len(observations['undocumented']),
            ))
        return messages

    def _l10n_pe_check_unique_keys(self, values_list, register):
        """SUNAT exige CUO + correlativo únicos dentro de cada registro."""
        counter = Counter((values['cuo'], values['correlative']) for values in values_list)
        return [
            _('%(register)s: CUO %(cuo)s con correlativo %(correlative)s repetido %(count)s veces.',
              register=register, cuo=cuo, correlative=correlative, count=count)
            for (cuo, correlative), count in counter.items() if count > 1
        ]

    def _l10n_pe_write_reports(self, cash_values, bank_values, warnings):
        self.ensure_one()
        report_cash = CashReport(self, cash_values)
        report_bank = BankReport(self, bank_values)
        cash_txt = report_cash.get_content_txt()
        bank_txt = report_bank.get_content_txt()

        messages = []
        if not cash_txt:
            messages.append(_('- No hay contenido en el registro "Detalle de los movimientos del efectivo" de este periodo.'))
        if not bank_txt:
            messages.append(_('- No hay contenido en el registro "Detalle de los movimientos de la cuenta corriente" de este periodo.'))
        messages += [f'- {warning}' for warning in warnings]

        self.write({
            'txt_binary_cash': base64.b64encode((cash_txt or '\n').encode()),
            'txt_filename_cash': report_cash.get_filename(file_type='txt'),
            'xls_binary_cash': base64.b64encode(report_cash.get_content_excel()),
            'xls_filename_cash': report_cash.get_filename(file_type='xlsx'),
            'txt_binary_bank': base64.b64encode((bank_txt or '\n').encode()),
            'txt_filename_bank': report_bank.get_filename(file_type='txt'),
            'xls_binary_bank': base64.b64encode(report_bank.get_content_excel()),
            'xls_filename_bank': report_bank.get_filename(file_type='xlsx'),
            'error_dialog': '\n'.join(messages),
            'date_ple': fields.Date.context_today(self),
            'state': 'load',
        })
