from odoo import _, api, models
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _skip_default_code_check(self):
        """
        Determina si este producto debe saltarse la validación de default_code.
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

    @api.constrains("default_code")
    def _check_default_code_required(self):
        for product in self:
            if product._skip_default_code_check():
                continue
            if not product.default_code or not product.default_code.strip():
                raise ValidationError(
                    _(
                        "La referencia interna es obligatoria para el producto '%(name)s'.",
                        name=product.display_name or product.name or product.id,
                    )
                )

    @api.constrains("default_code", "company_id")
    def _check_default_code_unique(self):
        """
        Unicidad por compañía, case-sensitive, validada a nivel Python.
        - Productos con misma compañía no pueden repetir default_code.
        - Productos sin compañía (compartidos) se validan entre sí.
        No usamos UNIQUE SQL por duplicados históricos existentes.
        """
        for product in self:
            if product._skip_default_code_check():
                continue
            code = product.default_code
            if not code:
                continue
            domain = [
                ("default_code", "=", code),
                ("id", "!=", product.id),
                ("company_id", "=", product.company_id.id if product.company_id else False),
            ]
            dup = self.sudo().with_context(active_test=False).search(domain, limit=1)
            if dup:
                raise ValidationError(
                    _(
                        "La referencia interna '%(code)s' ya está en uso por el producto "
                        "'%(name)s' (ID: %(id)s) en la misma compañía. Debe ser única.",
                        code=code,
                        name=dup.display_name,
                        id=dup.id,
                    )
                )