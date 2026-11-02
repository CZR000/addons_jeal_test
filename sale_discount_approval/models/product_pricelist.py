from odoo import models, api, _
from odoo.exceptions import UserError


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def _check_sales_manager_write_permission(self):
        """Check if current user has permission to create/modify pricelists."""
        if self.env.su:
            return
        if not self.env.user.is_sales_manager:
            raise UserError(
                _('Solo el Gerente de Ventas puede crear, modificar o eliminar '
                  'listas de precios.\n'
                  'Consulte con el administrador del sistema para obtener acceso.')
            )

    def write(self, vals):
        self._check_sales_manager_write_permission()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.is_sales_manager:
            raise UserError(
                _('Solo el Gerente de Ventas puede crear, modificar o eliminar '
                  'listas de precios.\n'
                  'Consulte con el administrador del sistema para obtener acceso.')
            )
        return super().create(vals_list)

    def unlink(self):
        self._check_sales_manager_write_permission()
        return super().unlink()
