import logging

from odoo import models, _

from ..reports.report_inv_bal_0308_0310 import (
    InvBal38ReportExcel,
    InvBal39ReportExcel,
    InvBal310ReportExcel,
)

_logger = logging.getLogger(__name__)


class PleReportInvBalBook0308To0310(models.Model):
    """Formatos 3.8, 3.9 y 3.10 del Libro de Inventarios y Balances."""

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_08(self):
        """Formato 3.8 - Inversiones mobiliarias (cuenta 30)."""
        return self._generate_single('08')

    def _prepare_report_08(self):
        self.ensure_one()
        return InvBal38ReportExcel(self, self._get_data_08())

    def action_generate_09(self):
        """Formato 3.9 - Intangibles (cuenta 34)."""
        return self._generate_single('09')

    def _prepare_report_09(self):
        self.ensure_one()
        return InvBal39ReportExcel(self, self._get_data_09())

    def action_generate_10(self):
        """Formato 3.10 - Tributos por pagar (cuenta 40)."""
        return self._generate_single('10')

    def _prepare_report_10(self):
        self.ensure_one()
        return InvBal310ReportExcel(self, self._get_data_10())

    # ------------------------------------------------------------------
    # DATA - Formato 3.8 Inversiones mobiliarias (cuenta 30)
    # ------------------------------------------------------------------
    def _get_data_08(self):
        """Valores al `date_end` por emisor y cuenta.

        - Costo total: saldo de las cuentas 30 (inversiones mobiliarias).
        - Provision total: saldo de la desvalorizacion de inversiones mobiliarias (367), en una fila
          propia por cuenta/emisor, en positivo.
        - Valor nominal unitario y cantidad de titulos no se registran en
          Odoo, por lo que se dejan en blanco.
        """
        self.ensure_one()
        cost_accounts = self._get_accounts_by_prefix(['30'])
        prov_accounts = self._get_accounts_by_prefix(['367'])
        all_accounts = cost_accounts | prov_accounts
        balances = self._balances_by_account_partner(self.date_end, all_accounts.ids)
        if not balances:
            return {'lines': [], 'total_cost': 0.0, 'total_provision': 0.0, 'total_net': 0.0}

        account_by_id = {a.id: a for a in all_accounts}
        partners = self.env['res.partner'].browse(
            [pid for (_aid, pid) in balances if pid]
        )
        partner_by_id = {p.id: p for p in partners}

        lines = []
        for (account_id, partner_id), balance in balances.items():
            if abs(balance) < 0.005:
                continue
            account = account_by_id[account_id]
            is_provision = account in prov_accounts
            doc_type, doc_number, name = self._partner_identity(
                partner_by_id.get(partner_id), _('VARIOS (sin emisor asignado)'),
            )
            cost = 0.0 if is_provision else balance
            provision = -balance if is_provision else 0.0
            lines.append({
                'doc_type': doc_type,
                'doc_number': doc_number,
                'name': name,
                'title': account.name or '',
                'nominal_value': None,
                'quantity': None,
                'cost': cost,
                'provision': provision,
                'net': cost - provision,
                'account_code': account.code or '',
            })

        lines.sort(key=lambda r: (r['account_code'], (r['name'] or '').upper()))
        return {
            'lines': lines,
            'total_cost': sum(r['cost'] for r in lines),
            'total_provision': sum(r['provision'] for r in lines),
            'total_net': sum(r['net'] for r in lines),
        }

    # ------------------------------------------------------------------
    # DATA - Formato 3.9 Intangibles (cuenta 34)
    # ------------------------------------------------------------------
    def _get_data_09(self):
        """Intangibles al `date_end`, una fila por clase de intangible del
        PCGE (341 concesiones/licencias, 342 patentes, 343 software, ...).

        Se agrupa por clase porque la amortizacion acumulada se registra por
        clase en la 396 (el 5to digito de la 396 es el 3er digito de la 34),
        y porque los cierres/aperturas anuales reagrupan los saldos por
        cuenta, sin detalle por item.

        - Valor contable: saldo de las cuentas 34 de la clase.
        - Amortizacion acumulada: saldo de las 396 de la clase, en positivo.
        - Fecha de inicio: primer cargo (debe) en las cuentas de la clase.
        - Tipo (Tabla 7): campo "Tipo de intangible" de la cuenta 34
          (01 - adquirido si no esta configurado).
        """
        self.ensure_one()
        cost_accounts = self._get_accounts_by_prefix(['34'])
        amort_accounts = self._get_accounts_by_prefix(['396'])
        balances = self._balances_by_account(
            self.date_end, (cost_accounts | amort_accounts).ids,
        )

        classes = {}
        for account in cost_accounts:
            cls = (account.code or '')[2:3]
            group = classes.setdefault(cls, {
                'accounts': self.env['account.account'],
                'cost': 0.0, 'amort': 0.0,
            })
            group['accounts'] |= account
            group['cost'] += balances.get(account.id, 0.0)
        for account in amort_accounts:
            cls = (account.code or '')[4:5]
            if cls in classes:
                classes[cls]['amort'] += -balances.get(account.id, 0.0)
            elif abs(balances.get(account.id, 0.0)) >= 0.005:
                _logger.warning(
                    'PLE Inv. y Balances 3.9 (%s): la cuenta %s no tiene una '
                    'clase de intangible (34) asociada.',
                    self.company_id.name, account.code,
                )

        start_dates = self._first_debit_date_by_account(cost_accounts.ids)

        lines = []
        for cls in sorted(classes):
            group = classes[cls]
            if abs(group['cost']) < 0.005 and abs(group['amort']) < 0.005:
                continue
            with_balance = group['accounts'].filtered(
                lambda a: abs(balances.get(a.id, 0.0)) >= 0.005
            ) or group['accounts']
            first = with_balance.sorted(lambda a: a.code or '')[:1]
            if len(with_balance) == 1:
                description = first.name or ''
            else:
                description = (first.name or '').split(' - ')[0]
            dates = [start_dates[a.id] for a in group['accounts'] if a.id in start_dates]
            intangible_type = next(
                (a.l10n_pe_intangible_type for a in with_balance
                 if a.l10n_pe_intangible_type),
                '01',
            )
            lines.append({
                'start_date': min(dates) if dates else False,
                'description': description,
                'intangible_type': intangible_type,
                'value': group['cost'],
                'amortization': group['amort'],
                'net': group['cost'] - group['amort'],
            })

        return {
            'lines': lines,
            'total_value': sum(r['value'] for r in lines),
            'total_amortization': sum(r['amortization'] for r in lines),
            'total_net': sum(r['net'] for r in lines),
        }

    # ------------------------------------------------------------------
    # DATA - Formato 3.10 Tributos por pagar (cuenta 40)
    # ------------------------------------------------------------------
    def _get_data_10(self):
        """Saldo final al `date_end` de cada subcuenta de la 40 con
        movimiento. El saldo se informa como (debe - haber), igual que el
        ejemplo de contabilidad: los tributos por pagar salen en negativo.
        """
        self.ensure_one()
        accounts = self._get_accounts_by_prefix(['40'])
        balances = self._balances_by_account(self.date_end, accounts.ids)
        lines = [
            {
                'code': account.code or '',
                'name': account.name or '',
                'balance': balances[account.id],
            }
            for account in accounts
            if account.id in balances
        ]
        return {
            'lines': lines,
            'total': sum(r['balance'] for r in lines),
        }

    # ------------------------------------------------------------------
    # Helpers del grupo (solo los usan estos formatos)
    # ------------------------------------------------------------------
    def _first_debit_date_by_account(self, account_ids):
        """Fecha del primer cargo (debe > 0) publicado por cuenta hasta
        `date_end`. Retorna {account_id: date}."""
        self.ensure_one()
        if not account_ids:
            return {}
        self.env.cr.execute("""
            SELECT aml.account_id, MIN(aml.date)
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE am.company_id = %(company)s
               AND am.state = 'posted'
               AND aml.date <= %(date_to)s
               AND aml.debit > 0
               AND aml.account_id IN %(accounts)s
             GROUP BY aml.account_id
        """, {
            'company': self.company_id.id,
            'date_to': self.date_end,
            'accounts': tuple(account_ids),
        })
        return dict(self.env.cr.fetchall())
