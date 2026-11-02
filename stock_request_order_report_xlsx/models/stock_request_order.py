from odoo import models


header = [
    "Fila",
    "Compañía",
    "Solicitud de existencias",
    "Pedido",
    "Producto",
    "Categoría",
    "Fecha prevista",
    "Política de Entrega",
    "Almacén",
    "Ubicación",
    "Ruta",
    "Área",
    "Estado",
    "Cant.",
    "Cant. a mano",
    "Cant. en progreso",
    "Cant. finalizada",
    "Cant. cancelada",
    "Comentario",
    "Estado",
    "Observaciones",
]


class StockRequestOrder(models.Model):
    _inherit = "stock.request.order"

    # ---------------------------------------------------------------------------- #
    #                                   MÉTODOS                                    #
    # ---------------------------------------------------------------------------- #
    def _get_data_stock_request(self):
        return self.env["stock.request"].search([("order_id", "=", self.id)])

    def __get_request_order_state(self):
        return self.env["stock.request"].fields_get(allfields=["state"])["state"]["selection"]

    def __get_request_order_picking_policy(self):
        return self.env["stock.request"].fields_get(allfields=["picking_policy"])["picking_policy"]["selection"]

    def _get_selection_display_name(self, data_selection, state_value):
        return next(
            (label for value, label in data_selection if value == state_value), ""
        )

    def _validate_field(self, value, empty_value=""):
        return value if value else empty_value

    def _get_data(self):
        form_header = []
        form_data = []
        data_stock_request = self._get_data_stock_request()
        data_picking_policy_selection = self.__get_request_order_picking_policy()
        data_state_selection = self.__get_request_order_state()

        # --------------------------------- CABECERA --------------------------------- #
        for record in self:
            state_header = self._get_selection_display_name(
                data_state_selection, record.state
            )
            form_header.append({
                "estado": self._validate_field(state_header),
                "pedido_existencia": self._validate_field(record.name),
                "fecha_prevista": str(self._validate_field(record.expected_date)),
                "politica_entrega": self._validate_field(record.picking_policy),
                "almacen": self._validate_field(record.warehouse_id.name),
                "ubicacion": self._validate_field(record.location_id.display_name),
                "companhia": self._validate_field(record.company_id.name),
            })

        # --------------------------------- ELEMENTOS -------------------------------- #
        for line in data_stock_request:
            picking_policy = self._get_selection_display_name(
                data_picking_policy_selection, line.picking_policy
            )
            state = self._get_selection_display_name(
                data_state_selection, line.state
            )
            form_data.append({
                "companhia": self._validate_field(line.company_id.name),
                "solicitud_existencia": self._validate_field(line.name),
                "pedido": self._validate_field(line.order_id.name),
                "producto": self._validate_field(line.product_id.display_name),
                "categoria": self._validate_field(line.categ_id.name),
                "fecha_prevista": str(self._validate_field(line.expected_date)),
                "politica_entrega": self._validate_field(picking_policy),
                "almacen": self._validate_field(line.warehouse_id.name),
                "ubicacion": self._validate_field(line.location_id.display_name),
                "ruta": self._validate_field(line.route_id.name),
                "area": self._validate_field(line.x_studio_rea_1),
                "estado_studio": self._validate_field(line.x_studio_estado),
                "cant": self._validate_field(line.product_uom_qty),
                "cant_mano": self._validate_field(line.x_studio_cantidad_a_mano),
                "cant_progreso": self._validate_field(line.qty_in_progress),
                "cant_finalizada": self._validate_field(line.qty_done),
                "cant_cancelada": self._validate_field(line.qty_cancelled),
                "comentario": self._validate_field(line.comment_editable),
                "estado": self._validate_field(state),
                "observaciones": self._validate_field(line.x_studio_observaciones),
            })

        return {
            "model": self._name,
            "header": header,
            "form_header": form_header,
            "form_data": form_data,
        }

    # ---------------------------------------------------------------------------- #
    #                                    BOTÓN                                     #
    # ---------------------------------------------------------------------------- #
    def get_excel_report(self):
        data = self._get_data()
        return self.env.ref(
            "stock_request_order_report_xlsx.action_report_stock_request_order_xlsx"
        ).report_action(self, data=data)