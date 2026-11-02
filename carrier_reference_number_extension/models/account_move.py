# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    carrier_ref_number = fields.Char(
        compute='_compute_carrier_ref_number',
        store=True,
        readonly=False,
    )

    @api.depends(
        'invoice_line_ids.sale_line_ids.order_id.picking_ids.state',
        'invoice_line_ids.sale_line_ids.order_id.picking_ids.l10n_latam_document_number',
    )
    def _compute_carrier_ref_number(self):
        """Rellena ``carrier_ref_number`` con las guías de remisión
        (``l10n_latam_document_number``) de los traslados asociados a las
        ventas de la factura, ignorando los cancelados.

        - Aplica solo a facturas y notas de crédito de cliente.
        - Concatena las guías con ``, `` deduplicando.
        - Si no hay guías, no toca el valor actual (respeta ediciones
          manuales previas cuando aún no hay traslados válidos).
        """
        for move in self:
            if move.move_type not in ('out_invoice', 'out_refund'):
                continue
            sale_orders = move.invoice_line_ids.sale_line_ids.order_id
            if not sale_orders:
                continue
            pickings = sale_orders.picking_ids.filtered(
                lambda p: p.state != 'cancel' and p.l10n_latam_document_number
            )
            seen = set()
            gr_numbers = []
            for gr in pickings.mapped('l10n_latam_document_number'):
                if gr and gr not in seen:
                    seen.add(gr)
                    gr_numbers.append(gr)
            if gr_numbers:
                move.carrier_ref_number = ', '.join(gr_numbers)
