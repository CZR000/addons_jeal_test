import logging

from odoo import models

_logger = logging.getLogger(__name__)

# En el estándar la moneda y la compañía de cada periodo salen de las líneas de
# logro (LEFT JOIN): los periodos sin logros quedan sin moneda y un plan en USD
# se mostraría con el símbolo de la compañía. Se toman del plan en ese caso.
PERIOD_FROM = 'FROM sale_commission_plan_target era'
PERIOD_REPLACEMENTS = [
    (PERIOD_FROM, f'{PERIOD_FROM}\n        JOIN sale_commission_plan period_plan ON period_plan.id = era.plan_id'),
    ('cl.company_id AS company_id,', 'COALESCE(cl.company_id, period_plan.company_id) AS company_id,'),
    ('cl.currency_id AS currency_id,', 'COALESCE(cl.currency_id, period_plan.currency_id) AS currency_id,'),
    ('        cl.company_id,\n        cl.currency_id\n',
     '        cl.company_id,\n        cl.currency_id,\n        period_plan.company_id,\n        period_plan.currency_id\n'),
]


class SaleCommissionReport(models.Model):
    _inherit = 'sale.commission.report'

    def _query(self):
        query = super()._query()
        if not all(old in query for old, _new in PERIOD_REPLACEMENTS):
            _logger.warning('sale.commission.report: la consulta estándar cambió, no se completa la moneda del plan.')
            return query
        for old, new in PERIOD_REPLACEMENTS:
            query = query.replace(old, new, 1)
        return query
