# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
import textwrap
import logging
import re


_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    """
    Esta clase gestiona la configuración visual y el contenido dinámico de las cotizaciones PDF.
    Diseñada para permitir al usuario funcional modificar textos legales y branding sin intervención técnica.
    """

    _inherit = "res.company"

    # ============================================================================
    # 1. GENERADORES DE CONTENIDO POR DEFECTO (TEMPLATES)
    # ============================================================================
    def _get_default_warranty_terms(self):
        """
        Genera la plantilla HTML para la tabla de Términos y Garantía.

        Diseño: Estilo 'Zebra' (filas alternadas) con bordes redondeados.
        Técnica: Se utiliza un 'div' contenedor con overflow:hidden para forzar el 
                 border-radius en wkhtmltopdf sin que los fondos de los <td> se desborden.

        Returns:
            str: HTML sanitizado con estilos inline para compatibilidad con wkhtmltopdf.
        """
        return textwrap.dedent(
            """
            <div style="border: 2px solid #000; border-radius: 14px; overflow: hidden; break-inside: avoid;">
                <table style="width: 100%; font-size: 14px; color: #000; border-collapse: collapse; margin: 0; border: none;">
                    <tbody>
                        <tr>
                            <td style="width: 30%; padding: 8px 14px; background: #E6E6E6; border-right: 2px solid #000; border-bottom: 2px solid #000;">
                                Garantía
                            </td>
                            <td style="width: 70%; padding: 8px 14px; border-bottom: 2px solid #000;">
                                1 año por defectos de fábrica.
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 14px; background: #E6E6E6; border-right: 2px solid #000; border-bottom: 2px solid #000;">
                                Plazo de Entrega
                            </td>
                            <td style="padding: 8px 14px; border-bottom: 2px solid #000;">
                                Entrega inmediata.
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 14px; background: #E6E6E6; border-right: 2px solid #000; border-bottom: 2px solid #000;">
                                Lugar de la entrega
                            </td>
                            <td style="padding: 8px 14px; border-bottom: 2px solid #000;">
                                En nuestros almacenes de Lima o Andahuaylas.
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 14px; background: #E6E6E6; border-right: 2px solid #000; border-bottom: 2px solid #000;">
                                Forma de pago
                            </td>
                            <td style="padding: 8px 14px; border-bottom: 2px solid #000;">
                                Contado.
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 14px; background: #E6E6E6; border-right: 2px solid #000; border-bottom: 2px solid #000;">
                                Validez de la oferta
                            </td>
                            <td style="padding: 8px 14px; border-bottom: 2px solid #000;">
                                7 días.
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 14px; background: #E6E6E6; border-right: 2px solid #000;">
                                Incluye
                            </td>
                            <td style="padding: 8px 14px;">
                                Capacitación del uso correcto del equipo<br/>
                                Certificado de capacitación<br/>
                                Regalo de Kit Minero<br/>
                                Regalo de Kit Merchandising<br/>
                                Llanta de repuesto<br/>
                                1 Gl de hidrolina
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """
        )
        
    def _get_default_bank_info(self):
        """
        Genera el bloque HTML de información bancaria basado en la lista definida.

        Returns:
            str: HTML formateado con las cuentas bancarias listas para renderizar.
        """
        # Obtenemos los datos estructurados
        accounts = self.get_formatted_bank_accounts_list()

        # Construimos las líneas HTML dinámicamente
        rows_html = ""
        for account in accounts:
            rows_html += f'<span style="margin: 3px 0;">{account["formatted_text"]}</span><br/>\n'

        return textwrap.dedent(
            f"""
            <div style="font-size: 16px; color: black; line-height: 1.4;">
                <span style="text-transform: uppercase;">
                    Números de Cuenta
                </span>
                <br/>
                {rows_html}
            </div>
        """
        )

    def _get_default_contact_footer(self):
        """
        Genera el pie de página corporativo con direcciones y contacto.
        """
        return textwrap.dedent(
            """
            <div style="text-align: center; font-size: 14px; color: black; line-height: 1;">
                <span>
                    OFICINA: CAL.TÚPAC AMARU NRO. 128 INT. 201 URB. JOSÉ BALTA LIMA - LIMA – MIRAFLORES
                </span>
                <br/>
                <span>
                    ALMACÉN ANDAHUAYLAS : AV. SESQUICENTENARIO NRO. 1496 (CP CHUMBAO) APURIMAC - ANDAHUAYLAS – ANDAHUAYLAS
                </span>
                <br/>
                <span>
                    CONTACTO: +51 993 655 071 / CORREO: VENTAS@CARGAMAX.PE
                </span>
                <br/>
                <span>
                    WWW.CARGAMAX.PE
                </span>
            </div>
        """
        )

    def _get_default_closing_message(self):
        """
        Genera el mensaje de cierre y despedida formal.
        """
        return textwrap.dedent(
            """
            <span style="font-size: 18px; color: black;">
                Quedamos a la espera de su orden de compra.
            </span>
        """
        )

    # ============================================================================
    # 2. CONFIGURACIÓN VISUAL (IMÁGENES Y BRANDING)
    # ============================================================================
    report_logo_main = fields.Binary(
        string="Logo Principal",
        attachment=True,
        help="Logo principal de la empresa.\n"
        "Recomendación UX: Usar formato PNG con fondo transparente.\n"
        "Dimensiones óptimas: 250x80 píxeles.",
    )

    report_logo_secondary = fields.Binary(
        string="Logo Secundario",
        attachment=True,
        help="Logo secundario o de certificación.\n"
        "Aparece en la esquina superior derecha del encabezado.\n"
        "Dimensiones óptimas: 200x80 píxeles.",
    )

    report_watermark = fields.Binary(
        string="Marca de Agua",
        attachment=True,
        help="Imagen de fondo para todas las páginas del reporte.\n"
        "Importante: Subir una imagen con opacidad baja (5-10%) para no dificultar la lectura del texto.\n"
        "Dimensiones óptimas: 800x800 píxeles.",
    )

    report_logo_bank_account = fields.Binary(
        string="Logo Cuenta de Banco",
        attachment=True,
        help="",
    )

    report_primary_color = fields.Char(
        string="Color Corporativo",
        default="#f29206",
        help="Color principal para encabezados de tablas, bordes y textos destacados.\n"
        "Formato requerido: Hexadecimal (ej. #f29206).",
    )

    # Opciones de visualización (Toggles)
    report_show_tax = fields.Boolean(
        string="Mostrar Desglose de Impuestos",
        default=True,
        help="Activar para detallar el IGV y otros impuestos en la sección de totales.",
    )

    report_show_page_numbers = fields.Boolean(
        string="Mostrar Paginación",
        default=True,
        help="Activar para mostrar 'Página X/Y' en el pie de página del documento.",
    )

    # Redes sociales URLs
    social_facebook_url = fields.Char(string="Facebook URL")
    social_instagram_url = fields.Char(string="Instagram URL")
    social_tiktok_url = fields.Char(string="TikTok URL")
    social_linkedin_url = fields.Char(string="LinkedIn URL")
    social_youtube_url = fields.Char(string="YouTube URL")

    # Iconos configurables
    social_facebook_icon = fields.Binary(string="Facebook Icono")
    social_instagram_icon = fields.Binary(string="Instagram Icono")
    social_tiktok_icon = fields.Binary(string="TikTok Icono")
    social_linkedin_icon = fields.Binary(string="LinkedIn Icono")
    social_youtube_icon = fields.Binary(string="YouTube Icono")

    # ============================================================================
    # 3. CONTENIDO DINÁMICO (EDITABLE)
    # ============================================================================
    report_warranty_terms = fields.Html(
        string="Términos y Garantía",
        translate=True,
        sanitize=True,
        default=lambda self: self._get_default_warranty_terms(),
        help="Tabla de condiciones comerciales.\n"
        "Este contenido se copiará por defecto en las nuevas cotizaciones, "
        "permitiendo al vendedor editarlo puntualmente si la negociación lo requiere.",
    )

    report_bank_accounts = fields.Html(
        string="Cuentas Bancarias",
        translate=True,
        sanitize=True,
        default=lambda self: self._get_default_bank_info(),
        help="Bloque de información bancaria.\n"
        "Se muestra en la parte inferior del reporte para facilitar el pago al cliente.",
    )

    report_contact_footer = fields.Html(
        string="Pie de Página (Contacto)",
        translate=True,
        sanitize=True,
        default=lambda self: self._get_default_contact_footer(),
        help="Información legal y de contacto.\n"
        "Aparece al final de cada página. Mantenga actualizada la dirección y teléfonos.",
    )

    report_closing_message = fields.Html(
        string="Mensaje de Despedida",
        translate=True,
        sanitize=True,
        default=lambda self: self._get_default_closing_message(),
        help="Texto de cortesía que aparece justo antes de la firma del vendedor.",
    )

    # ============================================================================
    # 4. VALIDACIONES Y RESTRICCIONES
    # ============================================================================
    @api.constrains("report_primary_color")
    def _check_hex_color_format(self):
        """
        Asegura que el color tenga un formato web válido para evitar errores en el PDF.
        """
        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for rec in self:
            if rec.report_primary_color and not hex_pattern.match(
                rec.report_primary_color
            ):
                raise ValidationError(
                    _(
                        "Error de Formato en Color Corporativo:\n"
                        "El valor '%s' no es válido.\n"
                        "Por favor, use un formato hexadecimal estándar (ejemplo: #f29206)."
                    )
                    % rec.report_primary_color
                )

    @api.constrains("report_logo_main", "report_logo_secondary", "report_watermark")
    def _check_image_file_size(self):
        """
        Evita la subida de imágenes excesivamente pesadas que puedan bloquear la generación del PDF.
        Límite establecido: 5MB.
        """
        MAX_MB = 5
        # Convertimos MB a bytes considerando el overhead de Base64 (~33%)
        MAX_BYTES = MAX_MB * 1024 * 1024 * 1.35

        for rec in self:
            images = {
                "Logo Principal": rec.report_logo_main,
                "Logo Secundario": rec.report_logo_secondary,
                "Marca de Agua": rec.report_watermark,
            }

            for label, image_data in images.items():
                if image_data and len(image_data) > MAX_BYTES:
                    # Calculamos el tamaño real aproximado para el mensaje
                    actual_size = len(image_data) / (1024 * 1024) / 1.35
                    raise ValidationError(
                        _(
                            "Archivo Demasiado Grande: %s\n\n"
                            "La imagen subida pesa %.2f MB, superando el límite seguro de %d MB.\n"
                            "Sugerencia: Comprima la imagen o redúzcala a un ancho de 1000px antes de subirla."
                        )
                        % (label, actual_size, MAX_MB)
                    )

    # ============================================================================
    # 5. LÓGICA DE NEGOCIO Y UTILIDADES
    # ============================================================================
    def get_formatted_bank_accounts_list(self):
        """
        Retorna las cuentas bancarias en formato estructurado.

        Returns:
            list[dict]: Lista de cuentas con estructura:
                - bank_name (str): Nombre corto del banco
                - bank_full_name (str): Nombre completo legal
                - currency (str): Código ISO de moneda (PEN, USD)
                - currency_symbol (str): Símbolo monetario (S/, $)
                - account_type (str): Tipo de cuenta (Corriente, Ahorros)
                - account_number (str): Número de cuenta formateado
                - cci (str): Código de Cuenta Interbancaria
                - formatted_text (str): Texto completo para renderizado directo
                - is_default (bool): Si es la cuenta principal

        """
        return [
            {
                "bank_name": "BCP",
                "bank_full_name": "Banco de Crédito del Perú",
                "currency": "PEN",
                "currency_symbol": "S/",
                "account_type": "Corriente",
                "account_number": "193-4204659-0-01",
                "cci": "00219300420465900116",
                "formatted_text": "BCP Cuenta Soles Corriente Nro. 193-4204659-0-01 // CCI 00219300420465900116",
                "is_default": True,
            },
            {
                "bank_name": "BCP",
                "bank_full_name": "Banco de Crédito del Perú",
                "currency": "USD",
                "currency_symbol": "$",
                "account_type": "Corriente",
                "account_number": "193-4220313-1-33",
                "cci": "00219300422031313311",
                "formatted_text": "BCP Cuenta Dólares Corriente Nro. 193-4220313-1-33 // CCI 00219300422031313311",
                "is_default": False,
            },
        ]

    def get_bank_account_by_currency(self, currency_code):
        """
        Selecciona la cuenta bancaria adecuada según la moneda de la transacción.

        Args:
            currency_code (str): Código ISO de la moneda (ej. 'PEN', 'USD').

        Returns:
            dict: Datos de la cuenta bancaria o la cuenta por defecto si no hay coincidencia.
        """
        accounts = self.get_formatted_bank_accounts_list()

        # 1. Búsqueda exacta por moneda
        for account in accounts:
            if account.get("currency") == currency_code:
                return account

        # 2. Fallback: Retornar la cuenta marcada como default o la primera disponible
        default_account = next((acc for acc in accounts if acc.get("is_default")), None)

        if not default_account and accounts:
            default_account = accounts[0]
            _logger.warning(
                "Moneda %s no encontrada. Usando primera cuenta disponible.",
                currency_code,
            )

        return default_account

    # ============================================================================
    # 6. ACCIONES DE MANTENIMIENTO
    # ============================================================================
    def action_reset_to_default_values(self):
        """
        Botón de Pánico: Restaura la configuración original.

        Útil si el usuario borra accidentalmente las tablas HTML o rompe el diseño.
        Muestra una notificación 'Toast' al finalizar.
        """
        self.ensure_one()
        try:
            self.write(
                {
                    "report_primary_color": "#f29206",
                    "report_warranty_terms": self._get_default_warranty_terms(),
                    "report_bank_accounts": self._get_default_bank_info(),
                    "report_contact_footer": self._get_default_contact_footer(),
                    "report_closing_message": self._get_default_closing_message(),
                    "report_show_tax": True,
                    "report_show_page_numbers": True,
                }
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Configuración Restaurada"),
                    "message": _(
                        "Se han restablecido los diseños y textos originales correctamente."
                    ),
                    "type": "success",
                    "sticky": False,  # Se oculta automáticamente
                },
            }
        except Exception as e:
            _logger.error("Error al restaurar configuración Cargamax: %s", str(e))
            raise ValidationError(
                _("No se pudo completar la restauración.\n" "Detalle técnico: %s")
                % str(e)
            )