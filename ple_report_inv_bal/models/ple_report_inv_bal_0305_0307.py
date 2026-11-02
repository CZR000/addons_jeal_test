import logging
from datetime import datetime, time

import pytz

from odoo import models

from ..reports.report_inv_bal_0305_0307 import (
    InvBal35ReportExcel,
    InvBal36ReportExcel,
    InvBal37ReportExcel,
)

_logger = logging.getLogger(__name__)


# Tabla 5 SUNAT (tipo de existencia) segun el prefijo de la cuenta
# contable. El formato 3.7 solo detalla las cuentas 20 (mercaderias) y
# 21 (productos terminados).
TABLA5_BY_ACCOUNT_PREFIX = {
    '20': '01',   # Mercaderias
    '21': '02',   # Productos terminados
}

COST_METHOD_LABELS = {
    'average': 'PROMEDIO PONDERADO',
    'fifo': 'PRIMERAS ENTRADAS, PRIMERAS SALIDAS (PEPS)',
    'standard': 'COSTO ESTÁNDAR',
}


class PleReportInvBalBook0305To0307(models.Model):
    """Formatos 3.5, 3.6 y 3.7 del Libro de Inventarios y Balances."""

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_05(self):
        """Formato 3.5 - Cuentas por cobrar diversas (cuenta 16)."""
        return self._generate_single('05')

    def _prepare_report_05(self):
        self.ensure_one()
        return InvBal35ReportExcel(self, self._get_data_05())

    def action_generate_06(self):
        """Formato 3.6 - Estimacion de cobranza dudosa (cuenta 19)."""
        return self._generate_single('06')

    def _prepare_report_06(self):
        self.ensure_one()
        return InvBal36ReportExcel(self, self._get_data_06())

    def action_generate_07(self):
        """Formato 3.7 - Mercaderias y productos terminados (20 y 21)."""
        return self._generate_single('07')

    def _prepare_report_07(self):
        self.ensure_one()
        return InvBal37ReportExcel(self, self._get_data_07())

    # ------------------------------------------------------------------
    # DATA - Formato 3.5 Cuentas por cobrar diversas (cuenta 16)
    # ------------------------------------------------------------------
    def _get_data_05(self):
        """Datos del formato 3.5 - Cuentas por cobrar diversas (cuenta 16)."""
        self.ensure_one()
        return self._get_open_items(['16'], date_source='invoice')

    # ------------------------------------------------------------------
    # DATA - Formato 3.6 Estimacion de cobranza dudosa (cuenta 19)
    # ------------------------------------------------------------------
    def _get_data_06(self):
        """Provisiones pendientes de la cuenta 19 al `date_end`, por deudor
        y documento. Las lineas sin tercero se muestran por asiento para
        no perder el numero de documento. El monto provisionado se muestra
        en positivo (la 19 tiene saldo natural acreedor)."""
        self.ensure_one()
        data = self._get_open_items(
            ['19'], date_source='invoice', split_no_partner=True,
        )
        for row in data['lines']:
            row['amount'] = -row['amount']
        data['total'] = -data['total']
        return data

    # ------------------------------------------------------------------
    # DATA - Formato 3.7 Mercaderias y productos terminados (cuentas 20 y 21)
    # ------------------------------------------------------------------
    def _get_data_07(self):
        """Detalle por producto del saldo contable de las cuentas 20 y 21
        al `date_end` (mismo criterio que el 3.1 y el 3.17: asientos
        publicados, sin el cierre de la fecha fin).

        - Costo total: saldo (debe - haber) de las lineas de las cuentas
          20/21 agrupado por cuenta y producto. El total del formato es
          siempre igual al saldo contable de esas cuentas.
        - Saldo sin producto (asientos manuales, reclasificaciones): una
          fila por cuenta.
        - Cantidad: existencia del kardex (stock.valuation.layer) a la
          fecha, porque las lineas contables no guardan una cantidad
          confiable. Costo unitario = costo total / cantidad, redondeado a
          2 decimales.
        - Tipo de existencia (Tabla 5): segun la cuenta (20 -> 01,
          21 -> 02).

        Retorna {'lines': [{code, existence_type, description, uom_code,
        quantity, unit_cost, total_cost}], 'total', 'method'}.
        """
        self.ensure_one()
        empty = {'lines': [], 'total': 0.0, 'method': ''}
        accounts = self._get_accounts_by_prefix(list(TABLA5_BY_ACCOUNT_PREFIX))
        if not accounts:
            return empty

        self.env.cr.execute("""
            SELECT aml.account_id, aml.product_id,
                   COALESCE(SUM(aml.debit - aml.credit), 0.0)
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE am.company_id = %(company)s
               AND am.state = 'posted'
               AND am.date <= %(date_to)s
               AND am.id NOT IN %(excluded)s
               AND aml.account_id IN %(accounts)s
             GROUP BY aml.account_id, aml.product_id
        """, {
            'company': self.company_id.id,
            'date_to': self.date_end,
            'excluded': self._get_excluded_move_ids(),
            'accounts': tuple(accounts.ids),
        })
        balances = [
            (account_id, product_id, float(balance or 0.0))
            for account_id, product_id, balance in self.env.cr.fetchall()
            if abs(float(balance or 0.0)) >= 0.005
        ]
        if not balances:
            return empty

        account_by_id = {a.id: a for a in accounts}
        product_ids = [pid for (_aid, pid, _bal) in balances if pid]
        products = self.env['product.product'].with_company(
            self.company_id
        ).with_context(active_test=False).browse(product_ids)
        product_by_id = {p.id: p for p in products}
        qty_by_product = self._kardex_qty_by_product(product_ids)

        lines = []
        methods = set()
        qty_used = set()
        for account_id, product_id, balance in balances:
            account = account_by_id[account_id]
            existence_type = TABLA5_BY_ACCOUNT_PREFIX.get((account.code or '')[:2], '')
            product = product_by_id.get(product_id)
            if product:
                methods.add(product.categ_id.property_cost_method)
                # La cantidad del kardex se informa una sola vez por producto.
                qty = 0.0 if product.id in qty_used else qty_by_product.get(product.id, 0.0)
                qty_used.add(product.id)
                uom = product.uom_id
                lines.append({
                    'code': product.default_code or '',
                    'existence_type': existence_type,
                    'description': product.name or '',
                    'uom_code': getattr(uom, 'l10n_pe_edi_measure_unit_code', False)
                                or uom.name or '',
                    'quantity': qty,
                    'unit_cost': round(balance / qty, 2) if abs(qty) > 1e-6 else 0.0,
                    'total_cost': balance,
                })
            else:
                lines.append({
                    'code': '',
                    'existence_type': existence_type,
                    'description': 'SALDO SIN PRODUCTO ASIGNADO - CUENTA %s' % (account.code or ''),
                    'uom_code': '',
                    'quantity': 0.0,
                    'unit_cost': 0.0,
                    'total_cost': balance,
                })

        lines.sort(key=lambda r: (r['code'] or '~', r['description'].upper()))
        method = ' / '.join(
            COST_METHOD_LABELS.get(m, (m or '').upper()) for m in sorted(m for m in methods if m)
        )
        return {
            'lines': lines,
            'total': sum(r['total_cost'] for r in lines),
            'method': method,
        }

    # ------------------------------------------------------------------
    # Helpers del grupo (solo los usan estos formatos)
    # ------------------------------------------------------------------
    def _kardex_qty_by_product(self, product_ids):
        """Cantidad en kardex (stock.valuation.layer) por producto al
        cierre de `date_end`. Retorna {product_id: cantidad}."""
        self.ensure_one()
        if not product_ids:
            return {}
        self.env.cr.execute("""
            SELECT svl.product_id, COALESCE(SUM(svl.quantity), 0.0)
              FROM stock_valuation_layer svl
             WHERE svl.company_id = %(company)s
               AND svl.create_date <= %(date_limit)s
               AND svl.product_id IN %(products)s
             GROUP BY svl.product_id
        """, {
            'company': self.company_id.id,
            'date_limit': self._end_of_day_utc(self.date_end),
            'products': tuple(set(product_ids)),
        })
        return {pid: float(qty or 0.0) for pid, qty in self.env.cr.fetchall()}

    def _end_of_day_utc(self, day):
        """Ultimo instante de `day` en la zona horaria del usuario,
        convertido a UTC naive (como se guarda create_date)."""
        tz = pytz.timezone(self.env.user.tz or 'America/Lima')
        local_end = tz.localize(datetime.combine(day, time.max))
        return local_end.astimezone(pytz.utc).replace(tzinfo=None)
