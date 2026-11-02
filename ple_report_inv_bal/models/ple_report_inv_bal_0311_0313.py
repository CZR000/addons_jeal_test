import logging

from odoo import models, _

from ..reports.report_inv_bal_0311_0313 import (
    InvBal311ReportExcel,
    InvBal312ReportExcel,
    InvBal313ReportExcel,
)

_logger = logging.getLogger(__name__)


class PleReportInvBalBook0311To0313(models.Model):
    """Formatos 3.11, 3.12 y 3.13 del Libro de Inventarios y Balances.

    Convencion de signo (igual que el 3.10 y los ejemplos de contabilidad):
    los saldos se informan como (debe - haber), por lo que los pasivos
    salen en negativo y el total coincide con el saldo contable.
    """

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_11(self):
        """Formato 3.11 - Remuneraciones y participaciones por pagar (41)."""
        return self._generate_single('11')

    def _prepare_report_11(self):
        self.ensure_one()
        return InvBal311ReportExcel(self, self._get_data_11())

    def action_generate_12(self):
        """Formato 3.12 - Proveedores (cuenta 42)."""
        return self._generate_single('12')

    def _prepare_report_12(self):
        self.ensure_one()
        return InvBal312ReportExcel(self, self._get_data_12())

    def action_generate_13(self):
        """Formato 3.13 - Cuentas por pagar diversas (46 y 47)."""
        return self._generate_single('13')

    def _prepare_report_13(self):
        self.ensure_one()
        return InvBal313ReportExcel(self, self._get_data_13())

    # ------------------------------------------------------------------
    # DATA - Formato 3.11 Remuneraciones y participaciones por pagar (cuenta 41)
    # ------------------------------------------------------------------
    def _get_data_11(self):
        """Saldo final al `date_end` por subcuenta de la 41 y trabajador
        (partner comercial). Las lineas sin tercero se agrupan en una fila
        "VARIOS" por subcuenta.

        Retorna {'lines': [{account_code, account_name, worker_code,
        worker_name, doc_type, doc_number, balance}], 'total'}.
        """
        self.ensure_one()
        accounts = self._get_accounts_by_prefix(['41'])
        balances = self._balances_by_account_partner(self.date_end, accounts.ids)
        if not balances:
            return {'lines': [], 'total': 0.0}

        account_by_id = {a.id: a for a in accounts}
        partners = self.env['res.partner'].browse(
            [pid for (_aid, pid) in balances if pid]
        )
        partner_by_id = {p.id: p for p in partners}

        lines = []
        for (account_id, partner_id), balance in balances.items():
            if abs(balance) < 0.005:
                continue
            account = account_by_id[account_id]
            partner = partner_by_id.get(partner_id)
            doc_type, doc_number, name = self._partner_identity(
                partner, _('VARIOS (sin trabajador asignado)'),
            )
            lines.append({
                'account_code': account.code or '',
                'account_name': account.name or '',
                'worker_code': doc_number,
                'worker_name': name,
                'doc_type': doc_type,
                'doc_number': doc_number,
                'balance': balance,
            })

        lines.sort(key=lambda r: (r['account_code'], (r['worker_name'] or '').upper()))
        return {
            'lines': lines,
            'total': sum(r['balance'] for r in lines),
        }

    # ------------------------------------------------------------------
    # DATA - Formato 3.12 Proveedores (cuenta 42)
    # ------------------------------------------------------------------
    def _get_data_12(self):
        """Datos del formato 3.12 - Proveedores (cuenta 42)."""
        self.ensure_one()
        return self._get_open_items(['42'], date_source='invoice')

    # ------------------------------------------------------------------
    # DATA - Formato 3.13 Cuentas por pagar diversas (cuentas 46 y 47)
    # ------------------------------------------------------------------
    def _get_data_13(self):
        """Datos del formato 3.13 - Cuentas por pagar diversas (46 y 47)."""
        self.ensure_one()
        return self._get_open_items(['46', '47'], date_source='invoice', split_no_partner=True)
