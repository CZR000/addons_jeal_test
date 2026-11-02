from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = "product.product"

    include_template_description = fields.Boolean(
        string="Incluir Descripción General",
        default=True,
        help="Si está activo, la descripción en la cotización incluirá tanto la descripción general del producto como la específica de esta variante.",
    )

    variant_description_sale = fields.Html(
        string="Descripción Específica de Variante",
        translate=True,
        sanitize=True,
        sanitize_attributes=False,
        help="Añada detalles técnicos específicos para esta variante (ej. Color, Talla, Voltaje) que se mostrarán en la cotización.",
    )

    custom_warranty_terms = fields.Html(
        string="Términos y Garantía (Personalizable)",
        compute="_compute_custom_warranty_terms",
        store=True,
        readonly=False,
        precompute=True,
        copy=False,
        sanitize=True,
        sanitize_attributes=False,
        help="Contenido dinámico de la cotización. Se inicializa con la plantilla de la compañía pero permite edición manual específica para esta venta.",
    )

    @api.depends("company_id")
    def _compute_custom_warranty_terms(self):
        """
        Calcula la plantilla inicial de garantía basada en la configuración de la compañía.
        Solo asigna valor si el campo está vacío.
        """
        for product in self:
            if product.company_id and not product.custom_warranty_terms:
                product.custom_warranty_terms = product.company_id.report_warranty_terms

    def action_reset_warranty_terms(self):
        """
        Restablece los términos de garantía personalizados usando la plantilla de la compañía.
        Soporta multi-registro y evita escrituras innecesarias en base de datos.
        """
        for product in self:
            template = product.company_id.report_warranty_terms

            if not template:
                raise UserError(
                    _("La compañía no tiene configurada una plantilla de términos de garantía.")
                )

            # Optimización ORM: Solo escribe si el valor difiere de la base de datos
            if product.custom_warranty_terms != template:
                product.custom_warranty_terms = template

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Plantilla restaurada"),
                "message": _("Se restablecieron los términos originales de la empresa."),
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    # ---------------------------------------------------------------------------- #
    #                            TODO - METODO HEREDADO                            #
    # ---------------------------------------------------------------------------- #
    # def get_product_multiline_description_sale(self):
    #     """ 
    #     Calcula la descripción de la línea de venta basándose en la configuración
    #     de la variante (Boolean) y los textos personalizados.
    #     """
    #     # 1. Obtenemos el nombre base (Ej: "[REF123] Laptop Gamer")
    #     name = self.display_name

    #     # 2. Lógica de Descripción General (Template)
    #     # El estándar solo hace: if self.description_sale...
    #     # Nosotros agregamos la condición de tu boolean:
    #     if self.include_template_description and self.description_sale:
    #         name += '\n' + self.description_sale

    #     # 3. Lógica de Descripción de Variante (Custom)
    #     if self.variant_description_sale:
    #         # NOTA IMPORTANTE: 
    #         # Como tu campo es HTML y la línea de pedido estándar (sale.order.line) 
    #         # suele esperar Texto, tenemos dos opciones.
            
    #         # Opción A: Si usas tu reporte PDF personalizado que renderiza HTML,
    #         # concatenamos directo (esto mostrará etiquetas <p> en la vista backend de Odoo).
    #         name += '\n' + self.variant_description_sale
            
    #         # Opción B (Recomendada si quieres limpieza en el backend): 
    #         # Convertir HTML a texto plano para la línea de pedido, 
    #         # pero mantienes el campo HTML para el reporte PDF si lo llamas directo.
    #         # name += '\n' + tools.html2plaintext(self.variant_description_sale)

    #     return name