from odoo import models, fields, api
from lxml import etree


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

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
    )
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
    signed_quantity = fields.Float(
        string="Cant. con signo",
        digits="Product Unit of Measure",
        compute="_compute_signed_quantity",
        store=True,
        help="Cantidad con signo basada en las ubicaciones de origen y destino.",
    )
    real_quantity = fields.Float(
        string="Cant. real",
        digits="Product Unit of Measure",
        compute="_compute_real_quantity",
        store=True,
        help="Cantidad real movida hacia/desde ubicaciones internas.",
    )
    remaining_qty = fields.Float(
        string="Cant. restante",
        digits="Product Unit of Measure",
        compute="_compute_stock_valuation_layers",
        store=True,
        help="Cantidad restante en las capas de valoración de stock asociadas.",
    )
    unit_cost = fields.Float(
        string="Val. unitario",
        digits="Product Price",
        compute="_compute_stock_valuation_layers",
        store=True,
        aggregator=False,
        help="Costo unitario basado en las capas de valoración de stock asociadas.",
    )
    value = fields.Monetary(
        string="Val. total",
        currency_field="company_currency_id",
        compute="_compute_stock_valuation_layers",
        store=True,
        help="Valor total basado en las capas de valoración de stock asociadas.",
    )
    remaining_value = fields.Monetary(
        string="Val. restante",
        currency_field="company_currency_id",
        compute="_compute_stock_valuation_layers",
        store=True,
        help="Valor restante basado en las capas de valoración de stock asociadas.",
    )
    company_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda de la empresa",
        related="company_id.currency_id",
        readonly=True,
    )

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)

        if view_type != "search":
            return arch, view

        if isinstance(arch, str):
            doc = etree.XML(arch)
        else:
            doc = arch

        filters_to_remove = [
            "todo",
            "incoming",
            "outgoing",
            "internal",
            "manufacturing",
            "inventory",
            "by_location",
        ]

        for filter_name in filters_to_remove:
            for node in doc.xpath(f"//filter[@name='{filter_name}']"):
                node.getparent().remove(node)

        separators = doc.xpath("//separator")
        for i in range(len(separators) - 1, 0, -1):
            current = separators[i]
            previous = separators[i - 1]

            if current.getprevious() == previous:
                current.getparent().remove(current)

        if isinstance(arch, str):
            arch = etree.tostring(doc, encoding="unicode")
        else:
            arch = doc

        if self.env.user.has_group(
            "stock_moves_history_fields.group_edit_code_movement_type"
        ):
            for node in arch.xpath("//field[@name='code_movement_type']"):
                if view_type == "form":
                    node.set("readonly", "0")

        return arch, view

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type="form", **options):
        key = super()._get_view_cache_key(view_id, view_type, **options)
        return key + (
            self.env.user.has_group(
                "stock_moves_history_fields.group_edit_code_movement_type"
            ),
        )

    @api.depends(
        "move_id.stock_valuation_layer_ids.code_movement_type",
        "move_id.stock_valuation_layer_ids.product_id",
        "move_id.stock_valuation_layer_ids.lot_id",
        "product_id",
        "lot_id",
    )
    def _compute_code_movement_type(self):
        for move_line in self:
            move_line.code_movement_type = "M"

            if not (move_line.move_id and move_line.product_id):
                continue

            product = move_line.product_id
            lot_id = move_line.lot_id
            check_lot = lot_id and product.lot_valuated

            layers = [
                l
                for l in move_line.move_id.stock_valuation_layer_ids
                if l.product_id == product and (not check_lot or l.lot_id == lot_id)
            ]

            if layers:
                move_line.code_movement_type = layers[0].code_movement_type

    def _inverse_code_movement_type(self):
        for move_line in self:
            if not (move_line.move_id and move_line.product_id):
                continue

            product = move_line.product_id
            lot_id = move_line.lot_id
            check_lot = lot_id and product.lot_valuated

            layers = move_line.move_id.stock_valuation_layer_ids.filtered(
                lambda l: l.product_id == product
                and (not check_lot or l.lot_id == lot_id)
            )

            if layers:
                layers.write({"code_movement_type": (move_line.code_movement_type)})

    @api.depends(
        "move_id",
        "move_id.scrapped",
        "location_id",
        "location_id.usage",
        "location_dest_id",
        "location_dest_id.usage",
    )
    def _compute_movement_type(self):
        for move_line in self:
            move_line.movement_type = move_line._get_movement_type()

    def _get_movement_type(self):
        self.ensure_one()

        if self.move_id and self.move_id.scrapped:
            return "scrap"

        src_usage = self.location_id.usage
        dst_usage = self.location_dest_id.usage

        if src_usage in ("internal", "transit") and dst_usage == "customer":
            return "outgoing_delivery"

        elif src_usage == "customer" and dst_usage in ("internal", "transit"):
            return "customer_return"

        elif src_usage == "supplier" and dst_usage in ("internal", "transit"):
            return "incoming_receipt"

        elif src_usage in ("internal", "transit") and dst_usage == "supplier":
            return "supplier_return"

        elif src_usage in ("internal", "transit") and dst_usage in (
            "internal",
            "transit",
        ):
            return "internal_transfer"

        elif src_usage == "inventory" or dst_usage == "inventory":
            return "inventory_adjustment"

        elif src_usage == "production" or dst_usage == "production":
            return "manufacturing"

        else:
            return "other"

    @api.depends(
        "quantity_product_uom",
        "location_id.usage",
        "location_dest_id.usage",
    )
    def _compute_signed_quantity(self):
        INTERNAL_USAGES = ("internal",)
        for line in self:
            qty = line.quantity_product_uom or 0.0
            src = line.location_id.usage or ""
            dst = line.location_dest_id.usage or ""

            if src in INTERNAL_USAGES and dst not in INTERNAL_USAGES:
                qty = -qty

            line.signed_quantity = qty

    @api.depends(
        "quantity_product_uom",
        "location_id.usage",
        "location_dest_id.usage",
    )
    def _compute_real_quantity(self):
        INTERNAL_USAGES = ("internal",)
        for line in self:
            qty = line.quantity_product_uom or 0.0
            src = line.location_id.usage or ""
            dst = line.location_dest_id.usage or ""

            src_internal = src in INTERNAL_USAGES
            dst_internal = dst in INTERNAL_USAGES

            if src_internal and not dst_internal:
                qty = -qty
            elif not src_internal and dst_internal:
                qty = qty
            else:
                qty = 0.0

            line.real_quantity = qty

    @api.depends(
        "move_id",
        "move_id.stock_valuation_layer_ids",
        "move_id.stock_valuation_layer_ids.remaining_qty",
        "move_id.stock_valuation_layer_ids.unit_cost",
        "move_id.stock_valuation_layer_ids.value",
        "move_id.stock_valuation_layer_ids.remaining_value",
        "move_id.stock_valuation_layer_ids.product_id",
        "move_id.stock_valuation_layer_ids.lot_id",
        "product_id",
        "lot_id",
    )
    def _compute_stock_valuation_layers(self):
        for move_line in self:
            move = move_line.move_id
            product = move_line.product_id

            if not move or not product:
                move_line.remaining_qty = 0.0
                move_line.unit_cost = 0.0
                move_line.value = 0.0
                move_line.remaining_value = 0.0
                continue

            layers = move.stock_valuation_layer_ids.filtered(
                lambda l: l.product_id and l.product_id.id == product.id
            )

            if move_line.lot_id and product.lot_valuated:
                layers = layers.filtered(
                    lambda l: l.lot_id and l.lot_id.id == move_line.lot_id.id
                )

            move_line.remaining_qty = sum((l.remaining_qty or 0.0) for l in layers)
            move_line.unit_cost = sum((l.unit_cost or 0.0) for l in layers)
            move_line.value = sum((l.value or 0.0) for l in layers)
            move_line.remaining_value = sum((l.remaining_value or 0.0) for l in layers)
