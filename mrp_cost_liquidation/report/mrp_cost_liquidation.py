from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import float_round, SQL


_STUDIO_CONTACT_FIELD = 'partner_id'
_INVOICE_MO_FIELD = 'mrp_production_id'
_ALLOWED_INVOICE_MOVE_TYPES = ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')


class MrpCostLiquidation(models.AbstractModel):
    _name = 'report.mrp_cost_liquidation.mrp_cost_liquidation'
    _description = 'Liquidación de costos'

    def _prepare_contact(self, productions):
        Production = self.env['mrp.production']
        if _STUDIO_CONTACT_FIELD not in Production._fields:
            return False
        if not productions or len(productions) != 1:
            return False
        production = productions[0]
        try:
            partner = production[_STUDIO_CONTACT_FIELD]
        except Exception:
            return False
        if not partner:
            return False
        return {
            'id': partner.id,
            'display_name': partner.display_name,
        }

    def _get_landed_cost_data(self, productions):
        """Devuelve los stock.landed.cost aplicados a las MOs del reporte.

        Compatibilidad Odoo 18 (cambios críticos):
            * `res.currency._get_query_currency_table({...})` fue ELIMINADO
              en v18. Ahora se usa `_get_simple_currency_table(companies)`
              que devuelve un objeto `SQL` representando la tabla
              `account_currency_table`.
              Verificado en: odoo/addons/account/models/res_currency.py:42
              Ejemplo de uso: enterprise/mrp_account_enterprise/reports/
                              mrp_cost_structure.py:18
            * Las queries ahora se componen con `odoo.tools.SQL("...",
              currency_table=ct, ...)` en lugar de f-strings.
            * El campo proyectado es `account_currency_table.rate` (no
              `currency_table.rate`).
            * `check_access_rights()` está deprecado en v18 (warning); usamos
              `has_access()` que es el reemplazo idiomático (models.py:4446).
        """
        res = {
            'costs_by_mo': defaultdict(lambda: self.env['stock.landed.cost']),
            'doc_info': {},
            'applied_by_mo': defaultdict(float),
            'applied_by_cost_mo': defaultdict(float),
        }

        if not productions:
            return res

        LandedCost = self.env['stock.landed.cost']
        if not LandedCost.has_access('read'):
            return res

        try:
            costs = LandedCost.search([
                ('target_model', '=', 'manufacturing'),
                ('mrp_production_ids', 'in', productions.ids),
                ('state', '=', 'done'),
            ])
        except AccessError:
            return res

        if not costs:
            return res

        prod_ids_set = set(productions.ids)
        for cost in costs:
            for mo in cost.mrp_production_ids:
                if mo.id in prod_ids_set:
                    res['costs_by_mo'][mo.id] |= cost

        # v18: SQL helper en lugar de f-string. Tabla `account_currency_table`.
        currency_table = self.env['res.currency']._get_simple_currency_table(
            self.env.companies
        )

        company_ids = costs.mapped('company_id').ids
        rate_by_company = defaultdict(lambda: 1.0)
        if company_ids:
            query = SQL(
                """
                SELECT account_currency_table.company_id, account_currency_table.rate
                FROM %(currency_table)s
                WHERE account_currency_table.company_id IN %(company_ids)s
                """,
                currency_table=currency_table,
                company_ids=tuple(company_ids),
            )
            self.env.cr.execute(query)
            for company_id, rate in self.env.cr.fetchall():
                rate_by_company[company_id] = rate or 1.0

        move_ids = productions.move_finished_ids.ids
        if move_ids:
            moves = self.env['stock.move'].browse(move_ids)
            move_to_mo = {m.id: (m.production_id.id or False) for m in moves}

            query = SQL(
                """
                SELECT
                    val.cost_id,
                    val.move_id,
                    SUM(val.additional_landed_cost) AS amount,
                    account_currency_table.rate
                FROM stock_valuation_adjustment_lines val
                JOIN stock_landed_cost cost ON cost.id = val.cost_id
                JOIN account_journal aj ON aj.id = cost.account_journal_id
                LEFT JOIN %(currency_table)s
                       ON account_currency_table.company_id = aj.company_id
                WHERE val.cost_id IN %(cost_ids)s
                  AND val.move_id IN %(move_ids)s
                GROUP BY val.cost_id, val.move_id, account_currency_table.rate
                """,
                currency_table=currency_table,
                cost_ids=tuple(costs.ids),
                move_ids=tuple(move_ids),
            )
            self.env.cr.execute(query)
            for cost_id, move_id, amount, rate in self.env.cr.fetchall():
                mo_id = move_to_mo.get(move_id)
                if not mo_id:
                    continue
                converted_amount = (amount or 0.0) * (rate or 1.0)
                if not converted_amount:
                    continue
                res['applied_by_mo'][mo_id] += converted_amount
                res['applied_by_cost_mo'][(cost_id, mo_id)] += converted_amount

        state_labels = dict(costs._fields['state']._description_selection(self.env))
        split_method_labels = {}
        if costs and costs._fields.get('cost_lines') and costs.cost_lines and costs.cost_lines._fields.get('split_method'):
            split_method_labels = dict(costs.cost_lines._fields['split_method']._description_selection(self.env))
        for cost in costs:
            rate = rate_by_company[cost.company_id.id]
            cost_lines_payload = []
            for cl in cost.cost_lines:
                cost_lines_payload.append({
                    'product_name': cl.product_id.display_name if cl.product_id else '',
                    'account_name': cl.account_id.display_name if cl.account_id else '',
                    'split_method': getattr(cl, 'split_method', '') or '',
                    'split_method_label': split_method_labels.get(getattr(cl, 'split_method', '') or '', getattr(cl, 'split_method', '') or ''),
                    'amount': (cl.price_unit or 0.0) * rate,
                })
            res['doc_info'][cost.id] = {
                'id': cost.id,
                'name': cost.name,
                'date': cost.date,
                'state': cost.state,
                'state_label': state_labels.get(cost.state, cost.state),
                'amount_total': (cost.amount_total or 0.0) * rate,
                'cost_lines': cost_lines_payload,
            }

        return res

    def _get_invoices_data(self, mos, contact=None):
        """Devuelve facturas asociadas a una(s) OF(s) mediante account.move.mrp_production_id.

        Reglas:
        - Muestra TODOS los documentos vinculados a la(s) OF(s) (cliente + proveedor).
        - Totales NETOS: facturas de cliente suman, notas de crédito de cliente restan;
          facturas de proveedor restan, notas de crédito de proveedor suman.
        - También retorna el total facturado al cliente (neto) en moneda de la compañía.

        Compatibilidad Odoo 18: `check_access_rights()` → `has_access()`
        (models.py:4446). El warning de deprecación rompería el flujo en
        modo --dev=all; usamos el método nuevo.
        """
        res = {
            'invoices': [],
            'totals_by_currency': [],
            'customer_totals_by_currency': [],
            'total_company_signed': 0.0,
            'customer_total_company': 0.0,
            'company_currency': False,
        }
        if not mos:
            return res

        AccountMove = self.env['account.move']
        if _INVOICE_MO_FIELD not in AccountMove._fields:
            return res
        if not AccountMove.has_access('read'):
            return res

        company = mos[:1].company_id
        company_currency = company.currency_id
        res['company_currency'] = company_currency

        domain = [
            ('state', '!=', 'cancel'),
            ('move_type', 'in', _ALLOWED_INVOICE_MOVE_TYPES),
            (_INVOICE_MO_FIELD, 'in', mos.ids),
        ]
        moves = AccountMove.search(domain, order='invoice_date desc, date desc, id desc')
        if not moves:
            return res

        state_labels = dict(AccountMove._fields['state']._description_selection(self.env))

        invoices_payload = []
        totals_by_currency = defaultdict(float)
        customer_totals_by_currency = defaultdict(float)
        currency_by_id = {}

        def _sign_all(move_type):
            if move_type == 'out_invoice':
                return 1
            if move_type == 'out_refund':
                return -1
            if move_type == 'in_invoice':
                return -1
            if move_type == 'in_refund':
                return 1
            return 0

        def _sign_customer(move_type):
            if move_type == 'out_invoice':
                return 1
            if move_type == 'out_refund':
                return -1
            return 0

        total_company_signed = 0.0
        customer_total_company = 0.0

        for inv in moves:
            inv_currency = inv.currency_id or company_currency
            currency_by_id[inv_currency.id] = inv_currency

            amount_total = inv.amount_total or 0.0
            sign_all = _sign_all(inv.move_type)
            sign_cust = _sign_customer(inv.move_type)

            signed_amount = amount_total * sign_all
            totals_by_currency[inv_currency.id] += signed_amount

            if sign_cust:
                customer_totals_by_currency[inv_currency.id] += amount_total * sign_cust

            inv_date = inv.invoice_date or inv.date or fields.Date.context_today(self)
            if inv_currency == company_currency:
                amount_company = amount_total
            else:
                amount_company = inv_currency._convert(amount_total, company_currency, company, inv_date)

            total_company_signed += amount_company * sign_all
            customer_total_company += amount_company * sign_cust

            invoices_payload.append({
                'id': inv.id,
                'name': inv.name if inv.name and inv.name != '/' else inv.display_name,
                'date': inv.invoice_date or inv.date,
                'partner_name': inv.partner_id.display_name if inv.partner_id else '',
                'state': inv.state,
                'state_label': state_labels.get(inv.state, inv.state),
                'amount_total': amount_total,
                'signed_amount': signed_amount,
                'currency': inv_currency,
                'move_type': inv.move_type,
            })

        res['invoices'] = invoices_payload
        res['totals_by_currency'] = [
            {'currency': currency_by_id[cid], 'amount_total': amt}
            for cid, amt in totals_by_currency.items()
        ]
        res['customer_totals_by_currency'] = [
            {'currency': currency_by_id[cid], 'amount_total': amt}
            for cid, amt in customer_totals_by_currency.items()
        ]
        res['total_company_signed'] = total_company_signed
        res['customer_total_company'] = customer_total_company
        return res

    @api.model
    def _get_report_values(self, docids, data=None):
        productions = self.env["mrp.production"].browse(docids).filtered(lambda p: p.state != "cancel")

        lines = []
        if productions and all(p.state == "done" for p in productions):
            lines = self.env["report.mrp_account_enterprise.mrp_cost_structure"].get_lines(productions) or []

        contact = self._prepare_contact(productions)

        landed_data = self._get_landed_cost_data(productions) or {}
        applied_by_mo = landed_data.get("applied_by_mo", {})
        applied_by_cost_mo = landed_data.get("applied_by_cost_mo", {})
        doc_info = landed_data.get("doc_info", {})
        costs_by_mo = landed_data.get("costs_by_mo", {})

        for line in lines:
            product = line.get("product")
            if not product:
                continue

            mos = productions.filtered(lambda m: m.product_id == product)
            mo_ids = mos.ids

            # --- Invoices data ---
            inv_data = self._get_invoices_data(mos, contact=contact) or {}
            line["invoices"] = inv_data.get("invoices") or []
            line["invoice_totals"] = inv_data.get("totals_by_currency") or []
            line["customer_invoice_totals"] = inv_data.get("customer_totals_by_currency") or []
            line["company_currency"] = inv_data.get("company_currency") or self.env.company.currency_id
            line["customer_invoiced_company"] = inv_data.get("customer_total_company") or 0.0
            line["invoice_total_company_signed"] = inv_data.get("total_company_signed") or 0.0
            line["operations_breakdown"] = self._get_operations_breakdown(mos)
            # --- Base (fabrication) cost ---
            fabrication_cost = line.get("total_cost") or 0.0
            line["fabrication_cost"] = fabrication_cost

            if not mo_ids:
                line["landed_costs"] = {"docs": [], "total_applied": 0.0}
                line["gross_profit"] = (line.get("customer_invoiced_company") or 0.0) - fabrication_cost
                continue

            # --- Landed costs (costos en destino) ---
            total_landed = sum(applied_by_mo.get(mo_id, 0.0) for mo_id in mo_ids)

            docs = []
            if total_landed:
                cost_ids = set()
                for mo_id in mo_ids:
                    for cost in costs_by_mo.get(mo_id, self.env["stock.landed.cost"]):
                        cost_ids.add(cost.id)

                for cost_id in sorted(cost_ids):
                    info = doc_info.get(cost_id)
                    if not info:
                        continue

                    applied_amt = sum(
                        applied_by_cost_mo.get((cost_id, mo_id), 0.0)
                        for mo_id in mo_ids
                    )
                    if not applied_amt:
                        continue

                    docs.append({**info, "applied_amount": applied_amt})

            line["landed_costs"] = {"docs": docs, "total_applied": total_landed}

            # --- Summary: fabricación vs facturado al cliente ---
            # Utilidad usando SOLO costo de fabricación (decisión del cliente).
            line["gross_profit"] = (line.get("customer_invoiced_company") or 0.0) - fabrication_cost

            # Si hay landed costs, suman al total_cost mostrado.
            if total_landed:
                line["total_cost"] = fabrication_cost + total_landed

                line.setdefault("total_cost_by_product", defaultdict(float))

                # Distribución del landed entre byproducts y producto principal.
                for mo in mos:
                    amt = applied_by_mo.get(mo.id, 0.0)
                    if not amt:
                        continue

                    for move in mo.move_byproduct_ids.filtered(
                        lambda mv: mv.state != "cancel" and mv.cost_share
                    ):
                        share = move.cost_share / 100.0
                        line["total_cost_by_product"][move.product_id] += amt * share

                    remaining_share = float_round(
                        1 - (sum(mo.move_finished_ids.mapped("cost_share")) / 100.0),
                        precision_rounding=0.0001,
                    )
                    line["total_cost_by_product"][product] += amt * remaining_share

        production = False
        if productions and len(productions) == 1:
            production = {"id": productions.id, "name": productions.name}

        return {
            "lines": lines,
            "contact": contact,
            "production": production,
        }

    def _get_operations_breakdown(self, mos):
        """Devuelve filas para la tabla de operaciones con desglose por hora.

        Regla de negocio:
          * Servicios (/h)    = workcenter.costs_hour
          * Mano de obra (/h) = workcenter.employee_costs_hour
          * Depreciación (/h) = workcenter.depreciation_costs_hour
          * Otros (/h)        = workcenter.other_costs_hour
        """
        res = []
        for wo in mos.workorder_ids.sorted(lambda w: (w.workcenter_id.name, w.name)):
            wc = wo.workcenter_id

            minutes = wo.duration or 0.0
            hours = minutes / 60.0 if minutes else 0.0

            service_hour = wc.costs_hour or 0.0
            labor_hour = getattr(wc, "employee_costs_hour", 0.0) or 0.0
            depreciation_hour = getattr(wc, "depreciation_costs_hour", 0.0) or 0.0
            other_hour = getattr(wc, "other_costs_hour", 0.0) or 0.0

            service_total = service_hour * hours
            labor_total = labor_hour * hours
            depreciation_total = depreciation_hour * hours
            other_total = other_hour * hours

            total_hour = service_hour + labor_hour + depreciation_hour + other_hour
            total_cost = service_total + labor_total + depreciation_total + other_total

            res.append({
                "workcenter": wc.display_name,
                "operation": wo.name,
                "hours": hours,
                "hour_service": service_hour,
                "hour_labor": labor_hour,
                "hour_depreciation": depreciation_hour,
                "hour_other": other_hour,
                "hour_total": total_hour,
                "cost_total": total_cost,
                "total_service": service_total,
                "total_labor": labor_total,
                "total_depreciation": depreciation_total,
                "total_other": other_total,
            })
        return res
