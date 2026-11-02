from odoo import api, models


class ReportLiquidationWebExt(models.AbstractModel):
    _inherit = 'report.account_liquidation.report_liquidation_web'

    @api.model
    def _get_report_values(self, docids, data=None):
        result = super()._get_report_values(docids, data=data)
        usd = self.env.ref('base.USD')
        LiqLine = self.env['account.liquidation.line']
        for r in result['report_docs']:
            for section_key in ('transport_lines', 'process_lines', 'invoiced_lines'):
                for line in r[section_key]:
                    liq_line = LiqLine.browse(line['line_id'])
                    line['total_usd'] = liq_line.total_usd
            r['transport_subtotal_usd'] = -sum(l['total_usd'] for l in r['transport_lines'])
            r['process_subtotal_usd'] = -sum(l['total_usd'] for l in r['process_lines'])
            r['invoiced_subtotal_usd'] = sum(l['total_usd'] for l in r['invoiced_lines'])
            r['grand_total_usd'] = (
                r['invoiced_subtotal_usd']
                + r['transport_subtotal_usd']
                + r['process_subtotal_usd']
            )
            r['usd_currency'] = usd
        return result
