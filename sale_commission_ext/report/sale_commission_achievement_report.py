from odoo import api, models

# Expresión nativa de los ajustes manuales (sale_commission): multiplica el
# importe por la tasa compañía -> moneda del ajuste, lo que invierte la conversión.
NATIVE_MANUAL_ACHIEVED = 'sca.currency_rate * sca.amount * scpa.rate'


class SaleCommissionAchievementReport(models.Model):
    """Los logros se expresan en la moneda del plan (sale.commission.report parte
    de estas mismas líneas, así que objetivos y comisiones quedan en esa moneda)."""
    _inherit = 'sale.commission.achievement.report'

    # -------------------------------------------------------------------------
    # Conversión a la moneda del plan (expresiones SQL)
    # -------------------------------------------------------------------------

    @api.model
    def _currency_rate_where(self):
        """Condición extra sobre res_currency_rate (alias r), p.ej. el tipo de tasa."""
        return ''

    @api.model
    def _currency_rate_subquery(self, currency, company, order, date_condition=''):
        # Mismo criterio que res.currency._get_rates: tasa de la compañía raíz o
        # global, la última hasta la fecha (o la primera, si no hay anterior).
        return f"""
            SELECT r.rate
              FROM res_currency_rate r
             WHERE r.currency_id = {currency}
               AND (r.company_id IS NULL OR r.company_id = (
                        SELECT split_part(c.parent_path, '/', 1)::int FROM res_company c WHERE c.id = {company}))
               {date_condition}
               {self._currency_rate_where()}
          ORDER BY r.company_id, r.name {order}, r.id {order}
             LIMIT 1
        """

    @api.model
    def _plan_currency_rate(self, plan_currency, company, date):
        """Unidades de la moneda del plan por unidad de la moneda de la compañía."""
        until_date = f'AND r.name <= {date}'
        return f"""
            CASE
                WHEN {plan_currency} = (SELECT c.currency_id FROM res_company c WHERE c.id = {company}) THEN 1.0
                ELSE COALESCE(
                    ({self._currency_rate_subquery(plan_currency, company, 'DESC', until_date)}),
                    ({self._currency_rate_subquery(plan_currency, company, 'ASC')}),
                    1.0)
            END
        """

    @api.model
    def _amount_in_plan_currency(self, amount, document_currency, company_amount, plan_currency, company, date):
        """Importe del documento en la moneda del plan: exacto si coinciden las
        monedas; si no, su importe en moneda de la compañía convertido al tipo de
        cambio de su fecha."""
        return f"""
            (CASE
                WHEN {document_currency} = {plan_currency} THEN {amount}
                ELSE {company_amount} * {self._plan_currency_rate(plan_currency, company, date)}
            END)
        """

    # -------------------------------------------------------------------------
    # Fuentes de logros
    # -------------------------------------------------------------------------

    @api.model
    def _get_invoice_rates_product(self):
        amount = self._amount_in_plan_currency(
            amount='aml.price_subtotal',
            document_currency='am.currency_id',
            # Importe contabilizado: respeta el tipo de cambio forzado de la
            # factura y no depende de invoice_currency_rate (en cero en facturas
            # de importe cero, lo que hacía fallar el estándar por división).
            company_amount="aml.balance * (CASE WHEN am.move_type = 'out_invoice' THEN -1 ELSE 1 END)",
            plan_currency='rules.currency_id',
            company='rules.company_id',
            date='am.date',
        )
        return f"""
            CASE
             WHEN am.move_type = 'out_invoice' THEN
                 rules.amount_invoiced_rate * {amount} +
                 rules.qty_invoiced_rate * aml.quantity
             WHEN am.move_type = 'out_refund' THEN
                 (rules.amount_invoiced_rate * {amount} +
                 rules.qty_invoiced_rate * aml.quantity) * -1
            END
        """

    @api.model
    def _get_sale_rates_product(self):
        amount = self._amount_in_plan_currency(
            amount='sol.price_subtotal',
            document_currency='so.currency_id',
            company_amount='sol.price_subtotal / NULLIF(so.currency_rate, 0)',
            plan_currency='rules.currency_id',
            company='rules.company_id',
            date='so.date_order::date',
        )
        return f"""
            rules.amount_sold_rate * {amount} +
            rules.qty_sold_rate * sol.product_uom_qty
        """

    @api.model
    def _where_invoices(self):
        # El estándar excluye solo las canceladas: los borradores también sumaban.
        return f"""{super()._where_invoices()}
          AND am.state = 'posted'
        """

    def _achievement_lines(self, users=None, teams=None):
        query, table = super()._achievement_lines(users, teams)
        amount = self._amount_in_plan_currency(
            amount='sca.amount',
            document_currency='sca.currency_id',
            company_amount='sca.amount / NULLIF(sca.currency_rate, 0)',
            plan_currency='scp.currency_id',
            company='scp.company_id',
            date='sca.date',
        )
        return query.replace(NATIVE_MANUAL_ACHIEVED, f'{amount} * scpa.rate'), table
