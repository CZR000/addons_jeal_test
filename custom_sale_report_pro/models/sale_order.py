# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import is_html_empty


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "exchange.rate.mixin"]

    custom_warranty_terms = fields.Html(
        string="Términos y Garantía (Personalizable)",
        compute="_compute_custom_warranty_terms",
        store=True,
        readonly=False,
        precompute=True,
        copy=False,
        sanitize=True,
        sanitize_attributes=False,
        help="""
            Contenido dinámico de la cotización. Se construye consolidando los términos y condiciones 
            de cada producto incluido en las líneas.
        """,
    )

    exchange_rate_date = fields.Date(
        string="Fecha del TC",
        tracking=True,
        help="""
            Fecha utilizada para calcular el tipo de cambio. 
            Si se define, se usará la tasa de sistema de esta fecha. 
            Si se deja vacío y no hay tasa forzada, se usará el flujo estándar.
        """,
    )

    report_employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado firma comercial",
        help="Empleado que aparecerá en el reporte.",
    )

    # ---------------------------------------------------------------------------- #
    #                     TODO - CONTRATO DEL MIXIN TC                             #
    # ---------------------------------------------------------------------------- #
    def _get_exchange_rate_context(self):
        """
        Implementación obligatoria del contrato del mixin.
        Retorna: (compañía, moneda_compañía, moneda_extranjera, fecha).
        """
        self.ensure_one()
        return (
            self.company_id,
            self.company_id.currency_id,
            self.currency_id or self.company_id.currency_id,
            self.exchange_rate_date or fields.Date.context_today(self),
        )

    @api.model
    def _get_exchange_rate_depends(self):
        """
        Declara dependencias para el mixin base.
        """
        return (
            "company_id.currency_id",
            "currency_id",
            "exchange_rate_date",
        )

    # ---------------------------------------------------------------------------- #
    #                                TODO - ONCHANGES                              #
    # ---------------------------------------------------------------------------- #
    @api.onchange("exchange_rate_date")
    def _onchange_exchange_rate_date(self):
        """
        Si selecciona fecha, limpiamos el forzado.
        """
        if self.exchange_rate_date and self.forced_exchange_rate:
            self.forced_exchange_rate = 0.0

    @api.onchange("forced_exchange_rate")
    def _onchange_forced_exchange_rate(self):
        """
        Si ingresa un monto forzado, limpiamos la fecha manual.
        """
        if self.forced_exchange_rate > 0 and self.exchange_rate_date:
            self.exchange_rate_date = False

    # ---------------------------------------------------------------------------- #
    #                              TODO - METODOS COMPUTE                          #
    # ---------------------------------------------------------------------------- #
    @api.depends("order_line.product_id")
    def _compute_custom_warranty_terms(self):
        """
        Calcula la plantilla inicial de garantía basada en los productos de las líneas.
        """
        for order in self:
            # Respetamos el contenido si ya existe y no está vacío (evita pisar trabajo manual)
            if not is_html_empty(order.custom_warranty_terms):
                continue

            order.custom_warranty_terms = order._build_warranty_terms_from_lines()

    # ============================================================================ #
    #                    TODO - METODOS ACCIONES DE INTERFAZ                       #
    # ============================================================================ #
    def action_reset_warranty_terms(self):
        """
        Restablecimiento Fuerte: Borra todo y lo reconstruye desde cero.
        """
        for order in self:
            consolidated_terms = order._build_warranty_terms_from_lines()

            if is_html_empty(consolidated_terms):
                raise UserError(
                    _("Ninguno de los productos actuales en la cotización tiene términos de garantía configurados.")
                )

            order.custom_warranty_terms = consolidated_terms

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "warning",
                "title": _("Restablecimiento completo"),
                "message": _("Se borraron las ediciones manuales y se reconstruyeron los términos desde cero."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_sync_missing_terms(self):
        """
        Sincronización Inteligente: Agrega los términos de los productos nuevos 
        al final del documento SIN borrar las ediciones manuales previas.
        """
        for order in self:
            current_html = order.custom_warranty_terms or ""
            appended_something = False
            
            valid_lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
            processed_products = set()

            for line in valid_lines:
                product = line.product_id
                
                if product.id not in processed_products and not is_html_empty(product.custom_warranty_terms):
                    # Buscamos si el nombre del producto ya existe dentro del HTML actual
                    if product.display_name not in current_html:
                        header = f"""
                        <div style="break-inside: avoid;" class="mb-4">
                            <h6 class="fw-bold mb-3" style="color: #4a4a4a; border-bottom: 1px solid #ccc; padding-bottom: 5px;">
                                Términos y condiciones de: <span class="text-dark">{product.display_name}</span>
                            </h6>
                            <div style="font-size: 13px;">
                                {product.custom_warranty_terms}
                            </div>
                        </div>
                        """
                        current_html += header
                        appended_something = True
                    
                processed_products.add(product.id)

            if appended_something:
                order.custom_warranty_terms = current_html
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "type": "success",
                        "title": _("Sincronización exitosa"),
                        "message": _("Se añadieron los términos de los nuevos productos al final del documento."),
                        "next": {"type": "ir.actions.act_window_close"},
                    },
                }
            else:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "type": "info",
                        "title": _("Sin cambios"),
                        "message": _("Todos los productos actuales ya tienen sus términos incluidos en el texto."),
                        "next": {"type": "ir.actions.act_window_close"},
                    },
                }

    # ============================================================================ #
    #                              TODO - MÉTODOS PRIVADOS                         #
    # ============================================================================ #
    def _build_warranty_terms_from_lines(self):
        """
        Método de utilidad que itera las líneas de la orden y construye
        el bloque HTML consolidado con títulos por producto.
        """
        self.ensure_one()
        html_parts = []
        
        valid_lines = self.order_line.filtered(lambda l: not l.display_type and l.product_id)
        processed_products = set()

        for line in valid_lines:
            product = line.product_id
            
            if product.id not in processed_products and not is_html_empty(product.custom_warranty_terms):                
                header = f"""
                <div style="break-inside: avoid;" class="mb-4">
                    <h6 class="fw-bold mb-3" style="color: #4a4a4a; border-bottom: 1px solid #ccc; padding-bottom: 5px;">
                        Términos y condiciones de: <span class="text-dark">{product.display_name}</span>
                    </h6>
                    <div style="font-size: 13px;">
                        {product.custom_warranty_terms}
                    </div>
                </div>
                """
                html_parts.append(header)
                processed_products.add(product.id)

        return "".join(html_parts)