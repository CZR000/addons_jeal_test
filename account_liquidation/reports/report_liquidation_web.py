from odoo import api, models


class ReportLiquidationWeb(models.AbstractModel):
    _name = 'report.account_liquidation.report_liquidation_web'
    _description = 'Reporte web de Liquidación'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['report.liquidation'].browse(docids)

        def _prepare_lines(lines):
            prepared = []
            for line in lines:
                move = line.move_id
                prepared.append({
                    'line_id': line.id,
                    'move_id': move.id if move else False,
                    'move_name': (move.name or move.ref) if move else (line.ref or ''),
                    'move_model': 'account.move',
                    'total_company': line.total_company or 0.0,
                    'currency_id': line.company_currency_id.id if line.company_currency_id else False,
                })
            return prepared

        report_docs = []
        for doc in docs:
            currency = doc.company_id.currency_id

            transport_lines = _prepare_lines(doc.transport_ids)
            process_lines = _prepare_lines(doc.process_ids)
            invoiced_lines = _prepare_lines(doc.invoiced_ids)

            transport_total = sum(l['total_company'] for l in transport_lines)
            process_total = sum(l['total_company'] for l in process_lines)
            invoiced_total = sum(l['total_company'] for l in invoiced_lines)

            transport_signed = -transport_total
            process_signed = -process_total
            invoiced_signed = invoiced_total

            grand_total = transport_signed + process_signed + invoiced_signed

            report_docs.append({
                'doc': doc,
                'currency': currency,
                'transport_lines': transport_lines,
                'process_lines': process_lines,
                'invoiced_lines': invoiced_lines,
                'transport_subtotal': transport_signed,
                'process_subtotal': process_signed,
                'invoiced_subtotal': invoiced_signed,
                'grand_total': grand_total,
            })

        return {
            'doc_ids': docids,
            'doc_model': 'report.liquidation',
            'docs': docs,
            'report_docs': report_docs,
        }
