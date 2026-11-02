import logging

from odoo import models, _

from ..reports.report_inv_bal_0314_0315 import (
    InvBal314ReportExcel,
    InvBal315ReportExcel,
)

_logger = logging.getLogger(__name__)


class PleReportInvBalBook0314To0315(models.Model):
    """Formatos 3.14 y 3.15 del Libro de Inventarios y Balances.

    Convencion de signo igual que 3.10 a 3.13: saldos como (debe - haber),
    de modo que el total coincide con el saldo contable.
    """

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_14(self):
        """Formato 3.14 - Beneficios sociales de los trabajadores (cuenta 47)."""
        return self._generate_single('14')

    def _prepare_report_14(self):
        self.ensure_one()
        return InvBal314ReportExcel(self, self._get_data_14())

    def action_generate_15(self):
        """Formato 3.15 - Ganancias diferidas (cuenta 49)."""
        return self._generate_single('15')

    def _prepare_report_15(self):
        self.ensure_one()
        return InvBal315ReportExcel(self, self._get_data_15())

    # ------------------------------------------------------------------
    # DATA - Formato 3.14 Beneficios sociales de los trabajadores (cuenta 47)
    # ------------------------------------------------------------------
    def _get_data_14(self):
        """Saldo final al `date_end` por trabajador de las cuentas 47
        (estructura del formato original del cliente). Las lineas sin
        tercero se agrupan en una fila "VARIOS".

        Retorna {'lines': [{doc_type, doc_number, name, balance}], 'total'}.
        """
        self.ensure_one()
        accounts = self._get_accounts_by_prefix(['47'])
        balances = self._balances_by_account_partner(self.date_end, accounts.ids)

        by_partner = {}
        for (_account_id, partner_id), balance in balances.items():
            by_partner[partner_id] = by_partner.get(partner_id, 0.0) + balance

        partners = self.env['res.partner'].browse([pid for pid in by_partner if pid])
        partner_by_id = {p.id: p for p in partners}

        lines = []
        for partner_id, balance in by_partner.items():
            if abs(balance) < 0.005:
                continue
            doc_type, doc_number, name = self._partner_identity(
                partner_by_id.get(partner_id), _('VARIOS (sin trabajador asignado)'),
            )
            lines.append({
                'doc_type': doc_type,
                'doc_number': doc_number,
                'name': name,
                'balance': balance,
            })

        lines.sort(key=lambda r: (r['name'] or '').upper())
        return {
            'lines': lines,
            'total': sum(r['balance'] for r in lines),
        }

    # ------------------------------------------------------------------
    # DATA - Formato 3.15 Ganancias diferidas (cuenta 49)
    # ------------------------------------------------------------------
    def _get_data_15(self):
        """Saldo final al `date_end` por subcuenta de la 49.

        La cuenta 49 no es conciliable y los cierres/aperturas
        anuales reagrupan sus saldos por cuenta, por lo que el detalle es
        por subcuenta. El numero de comprobante relacionado se informa
        como "-".

        Retorna {'lines': [{concept, doc_ref, balance}], 'total'}.
        """
        self.ensure_one()
        accounts = self._get_accounts_by_prefix(['49'])
        balances = self._balances_by_account(self.date_end, accounts.ids)
        lines = [
            {
                'concept': '%s %s' % (account.code or '', account.name or ''),
                'doc_ref': '-',
                'balance': balances[account.id],
            }
            for account in accounts
            if abs(balances.get(account.id, 0.0)) >= 0.005
        ]
        return {
            'lines': lines,
            'total': sum(r['balance'] for r in lines),
        }
