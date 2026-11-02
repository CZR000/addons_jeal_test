import logging

from odoo import models

from ..reports.report_inv_bal_0302_0304 import (
    InvBal32ReportExcel,
    InvBal33ReportExcel,
    InvBal34ReportExcel,
)

_logger = logging.getLogger(__name__)


class PleReportInvBalBook0302To0304(models.Model):
    """Formatos 3.2, 3.3 y 3.4 del Libro de Inventarios y Balances."""

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_02(self):
        """Formato 3.2 - Detalle de la cuenta 10 (Efectivo)."""
        return self._generate_single('02')

    def _prepare_report_02(self):
        self.ensure_one()
        return InvBal32ReportExcel(self, self._get_data_02())

    def action_generate_03(self):
        """Formato 3.3 - Detalle de la cuenta 12 (Clientes)."""
        return self._generate_single('03')

    def _prepare_report_03(self):
        self.ensure_one()
        return InvBal33ReportExcel(self, self._get_data_03())

    def action_generate_04(self):
        """Formato 3.4 - Detalle de la cuenta 14 (Personal y accionistas)."""
        return self._generate_single('04')

    def _prepare_report_04(self):
        self.ensure_one()
        return InvBal34ReportExcel(self, self._get_data_04())

    # ------------------------------------------------------------------
    # DATA - Formato 3.2 Efectivo y equivalente de efectivo (cuenta 10)
    # ------------------------------------------------------------------
    def _get_data_02(self):
        """Saldo final de cada cuenta divisionaria de la 10 al `date_end`,
        con su entidad financiera (Tabla 3), numero de cuenta y moneda
        (Tabla 4) tomados del diario de banco/caja asociado."""
        self.ensure_one()
        accounts = self._get_accounts_by_prefix(['10'])
        if not accounts:
            return {'lines': [], 'total_debit': 0.0, 'total_credit': 0.0}

        balances = self._balances_by_account(self.date_end, accounts.ids)

        journals = self.env['account.journal'].with_company(
            self.company_id
        ).search([
            ('company_id', '=', self.company_id.id),
            ('type', 'in', ('bank', 'cash')),
            ('default_account_id', 'in', accounts.ids),
        ])
        journal_by_account = {}
        for journal in journals:
            journal_by_account.setdefault(journal.default_account_id.id, journal)

        company_currency = self.company_id.currency_id
        lines = []
        total_debit = total_credit = 0.0
        for account in accounts:
            balance = balances.get(account.id, 0.0)
            if abs(balance) < 0.005:
                continue

            journal = journal_by_account.get(account.id)
            bank_account = journal.bank_account_id if journal else False
            bank = bank_account.bank_id if bank_account else False
            bank_code = (
                getattr(bank, 'sunat_bank_code', False)
                or getattr(bank, 'l10n_pe_edi_code', False)
                or '99'
            ) if bank else '99'
            currency = (
                (journal.currency_id if journal else False)
                or account.currency_id
                or company_currency
            )

            debit = balance if balance > 0 else 0.0
            credit = -balance if balance < 0 else 0.0
            total_debit += debit
            total_credit += credit
            lines.append({
                'code': account.code or '',
                'name': account.name or '',
                'bank_code': bank_code,
                'account_number': (bank_account.acc_number if bank_account else '') or '-',
                'currency': currency.name or '',
                'debit': debit,
                'credit': credit,
            })

        return {
            'lines': lines,
            'total_debit': total_debit,
            'total_credit': total_credit,
        }

    # ------------------------------------------------------------------
    # DATA - Formato 3.3 Clientes (cuenta 12)
    # ------------------------------------------------------------------
    def _get_data_03(self):
        """Datos del formato 3.3 - Detalle de la cuenta 12 (Clientes)."""
        self.ensure_one()
        return self._get_open_items(['12'], date_source='invoice')

    # ------------------------------------------------------------------
    # DATA - Formato 3.4 Personal y accionistas (cuenta 14)
    # ------------------------------------------------------------------
    def _get_data_04(self):
        """Datos del formato 3.4 - Detalle de la cuenta 14 (Personal y accionistas)."""
        self.ensure_one()
        return self._get_open_items(['14'], date_source='move')
