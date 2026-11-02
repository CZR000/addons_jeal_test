from odoo import _, api, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _skip_default_code_check(self):
        """
        Determina si esta plantilla debe saltarse la validación de default_code.
        Casos que se saltan:
        - Servicios técnicos internos de Odoo (Descuento global de Sale,
          producto de Envío de Delivery, recompensas de Loyalty, etc.).
          Se identifican por type='service'.
        - Carga de datos durante instalación o actualización de módulos
          (context 'install_mode' seteado por Odoo al procesar data files).
        """
        self.ensure_one()
        if self.type == 'service':
            return True
        if self.env.context.get('install_mode'):
            return True
        return False
