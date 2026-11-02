from odoo import models, fields, api


class StockMove(models.Model):
    _inherit = "stock.move"

    movement_type = fields.Selection(
        selection=[
            ("incoming_receipt", "Entrada - Recepción"),
            ("outgoing_delivery", "Salida - Entrega"),
            ("customer_return", "Devolución de cliente"),
            ("supplier_return", "Devolución a proveedor"),
            ("internal_transfer", "Transferencia interna"),
            ("inventory_adjustment", "Ajuste de inventario"),
            ("manufacturing", "Fabricación"),
            ("mrp_consumption_raw_materials", "Fabricación - Consumo de MP"),
            ("mrp_finished_product", "Fabricación - Producto terminado"),
            ("mrp_byproduct", "Fabricación - Subproducto"),
            ("dismantling", "Desmantelamiento"),
            ("dismantling_product", "Desmantelamiento - Producto"),
            ("dismantling_component", "Desmantelamiento - Componente recuperado"),
            ("repair", "Reparación"),
            ("scrap", "Desecho"),
            ("other", "Otro"),
        ],
        string="Tipo de movimiento",
        compute="_compute_movement_type",
        store=True,
        help="Tipo de movimiento de stock basado en las ubicaciones de origen y destino.",
    )
    code_movement_type = fields.Selection(
        string="Código de movimiento",
        selection=[
            ("A", "A"),
            ("M", "M"),
            ("C", "C"),
        ],
        compute="_compute_code_movement_type",
        inverse="_inverse_code_movement_type",
        store=True,
        readonly=True,
    )

    @api.depends("move_line_ids.movement_type")
    def _compute_movement_type(self):
        for move in self:
            types = set(move.move_line_ids.mapped("movement_type")) - {False}

            if len(types) == 1:
                move.movement_type = next(iter(types))
            else:
                move.movement_type = False

    @api.depends('picking_id.code_movement_type')
    def _compute_code_movement_type(self):
        for move in self:
            move.code_movement_type = (
                move.picking_id.code_movement_type or 'M'
            )

    def _inverse_code_movement_type(self):
        pass
