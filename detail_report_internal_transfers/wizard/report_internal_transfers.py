# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ReportInternalTransfers(models.TransientModel):
    _name = "report.internal.transfers"
    _description = "Informe Detalle de Transferencias Internas"

    # MÉTODOS DE SELECCIÓN DINÁMICA
    @api.model
    def _get_picking_states(self):
        """
        Obtiene dinámicamente los estados de stock.picking
        """
        return self.env["stock.picking"]._fields["state"].selection

    @api.model
    def _get_operation_types(self):
        """
        Obtiene dinámicamente los tipos de operación de stock.picking.type
        """
        return self.env["stock.picking.type"]._fields["code"].selection

    # CAMPOS
    type = fields.Selection(
        selection=[
            ("date", "Fecha"),
            ("transfer", "Transferencia"),
        ],
        string="Filtrar por",
        default="date",
        required=True,
    )

    date_start = fields.Date(
        string="Fecha Inicio",
        default=fields.Date.today,
    )

    date_end = fields.Date(
        string="Fecha Fin",
        default=fields.Date.today,
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    state = fields.Selection(
        selection="_get_picking_states",
        string="Estado",
        default="done",
        required=True,
    )

    operation_type = fields.Selection(
        selection="_get_operation_types",
        string="Tipo de operación",
        default="internal",
        required=True,
    )

    types_operations_ids = fields.Many2many(
        comodel_name="stock.picking.type",
        string="Tipos de Operaciones",
        domain="[('company_id', '=', company_id), ('code', '=', operation_type)]",
        required=True,
    )

    transferencia_ids = fields.Many2many(
        comodel_name="stock.picking",
        string="Transferencia",
        domain="[('state', '=', state), ('company_id', '=', company_id), ('picking_type_id', 'in', types_operations_ids)]",
    )

    product_ids = fields.Many2many(
        comodel_name="product.product",
        string="Productos",
    )

    # ---------------------------------------------------------------------------- #
    #                            TODO - METODOS ONCHANGE                           #
    # ---------------------------------------------------------------------------- #
    @api.onchange("type")
    def _onchange_type(self):
        if self.type == "date":
            self.transferencia_ids = False
        elif self.type == "transfer":
            self.date_start = False
            self.date_end = False

    @api.onchange("company_id", "operation_type")
    def _onchange_reset_types_operations_ids(self):
        if self.company_id and self.operation_type:
            types = self.env["stock.picking.type"].search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("active", "=", True),
                    ("code", "=", self.operation_type),
                ]
            )
            self.types_operations_ids = types.ids if types else False

    # ---------------------------------------------------------------------------- #
    #                                TODO - METODOS                                #
    # ---------------------------------------------------------------------------- #
    def _get_data(self):
        """
        Recopila la data para mandarla al reporte
        """
        domain_picking = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", self.state),
            ("picking_type_id", "in", self.types_operations_ids.ids),
        ]

        if self.transferencia_ids:
            domain_picking.append(("id", "in", self.transferencia_ids.ids))
        elif self.date_start and self.date_end:
            if self.date_start > self.date_end:
                raise ValidationError(
                    _("La fecha de inicio no puede ser mayor que la fecha de fin.")
                )
            domain_picking.extend(
                [
                    ("date_done", ">=", self.date_start),
                    ("date_done", "<=", self.date_end),
                ]
            )

        pickings = self.env["stock.picking"].search(domain_picking)

        domain_moves = [("picking_id", "in", pickings.ids)]
        if self.product_ids:
            domain_moves.append(("product_id", "in", self.product_ids.ids))

        moves = self.env["stock.move"].search(
            domain_moves, order="picking_type_id desc"
        )

        # Pre-cargamos todas las compras en una sola query
        products = moves.mapped("product_id")
        po_lines = self.env["purchase.order.line"].search(
            [
                ("state", "in", ["purchase", "done"]),
                ("product_id", "in", products.ids),
            ],
            order="id DESC",
        )

        # Armamos un diccionario con la última compra por producto
        last_po_by_product = {}
        for pol in po_lines:
            if pol.product_id not in last_po_by_product:
                last_po_by_product[pol.product_id] = pol

        # Obtenemos las traducciones de los estados
        state_dict = dict(self._fields["state"]._description_selection(self.env))

        form_data = []
        for line in moves:
            picking = line.picking_id
            product = line.product_id
            last_purchase = last_po_by_product.get(product)

            form_data.append(
                {
                    "compania": picking.company_id.name or "",
                    "contacto": picking.partner_id.name or "",
                    "referencia": picking.name or "",
                    "tipo_operacion": picking.picking_type_id.display_name or "",
                    "fecha_efectiva": picking.date_done,
                    "documento_origen": picking.origin or "",
                    "ubicacion_destino": picking.location_dest_id.complete_name or "",
                    "ubicacion_origen": picking.location_id.complete_name or "",
                    "estado": state_dict.get(picking.state, picking.state),
                    "categoria_producto": product.categ_id.display_name or "",
                    "producto": product.display_name or "",
                    "realizado": line.quantity,
                    "udm": line.product_uom.name or "",
                    "referencia_pedido": (
                        last_purchase.order_id.name if last_purchase else ""
                    ),
                    "fecha_confirmacion": (
                        last_purchase.date_approve if last_purchase else False
                    ),
                    "proveedor": last_purchase.partner_id.name if last_purchase else "",
                    "cantidad_total": (
                        last_purchase.product_uom_qty if last_purchase else 0.0
                    ),
                    "precio_unitario": (
                        last_purchase.price_unit if last_purchase else 0.0
                    ),
                    "impuestos": (
                        last_purchase.taxes_id.display_name if last_purchase else ""
                    ),
                    "moneda": (
                        last_purchase.order_id.currency_id.name if last_purchase else ""
                    ),
                }
            )

        return {
            "form_data": form_data,
            "start_date": self.date_start,
            "end_date": self.date_end,
        }

    # ---------------------------------------------------------------------------- #
    #                            TODO - METODOS ACCIONES                           #
    # ---------------------------------------------------------------------------- #
    def action_print_xlsx(self):
        """ 
        Dispara el reporte XLSX nativo asegurando contexto único 
        """
        self.ensure_one()
        return self.env.ref(
            "detail_report_internal_transfers.action_report_internal_transfers_xlsx"
        ).report_action(self, data=self._get_data())
        
    def action_print_pdf(self):
        """
        Dispara el reporte PDF nativo asegurando contexto único 
        """
        self.ensure_one()
        return self.env.ref(
            "detail_report_internal_transfers.action_report_internal_transfers_pdf"
        ).report_action(self, data=self._get_data())
