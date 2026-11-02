# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # Vínculo real con la recepción que porta la guía de transporte
    guia_picking_id = fields.Many2one(
        'stock.picking',
        string='Recepción / Guía de transporte',
        domain=[('transportista_id', '!=', False)],
        copy=False,
    )

    # Campos derivados del picking — readonly, siempre sincronizados
    ticket_pesaje = fields.Char(
        string='Ticket de pesaje',
        related='guia_picking_id.ticket_pesaje',
        readonly=True,
        store=True,
    )
    guias_gtr = fields.Char(
        string='Guías GTR',
        related='guia_picking_id.guias_gtr',
        readonly=True,
        store=True,
    )
    guias_grr = fields.Char(
        string='Guías GRR',
        related='guia_picking_id.guias_grr',
        readonly=True,
        store=True,
    )
    placa = fields.Char(
        string='Placa',
        related='guia_picking_id.placa',
        readonly=True,
        store=True,
    )

    @api.onchange('guia_picking_id')
    def _onchange_guia_picking_id(self):
        if not self.guia_picking_id:
            return
    
        picking = self.guia_picking_id
    
        if picking.transportista_id:
            self.partner_id = picking.transportista_id

        self._load_lines_from_picking(picking)
    
    def _load_lines_from_picking(self, picking):
        """Reemplaza order_line con líneas derivadas de los moves del picking,
        aplicando conversión producto + factor cuando exista."""
        Conversion = self.env['jeal.product.conversion']
    
        # 1) Consolidar por producto DESTINO
        quantities = {}
        for move in picking.move_ids:
            if move.state == 'cancel' or not move.product_id:
                continue
    
            src_product = move.product_id
            qty_received = move.product_qty
    
            conv = Conversion._get_conversion(src_product, company=self.company_id)
            if conv:
                target_product = conv.product_target_id
                qty_final = qty_received * conv.factor
            else:
                target_product = src_product
                qty_final = qty_received
    
            quantities.setdefault(target_product, 0.0)
            quantities[target_product] += qty_final
    
        # 2) Armar líneas con vals directos — sin invocar computes en NewId
        commands = [(5, 0, 0)]
        for product, qty in quantities.items():
            taxes = product.supplier_taxes_id.filtered(
                lambda t: not t.company_id or t.company_id == self.company_id
            )
            commands.append((0, 0, {
                'product_id': product.id,
                'name': product.display_name,
                'product_qty': qty,
                'product_uom': product.uom_po_id.id or product.uom_id.id,
                'price_unit': product.standard_price,
                'taxes_id': [(6, 0, taxes.ids)],
                'date_planned': fields.Datetime.now(),
            }))
    
        self.order_line = commands

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.ticket_pesaje:
            vals['payment_reference'] = self.ticket_pesaje
        return vals