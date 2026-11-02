# discount_fixed
from odoo import models, fields, api


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Campo para ingresar el monto fijo
    discount_fixed = fields.Monetary(
        string="Desc. Fijo ($)",

        help="Monto fijo a descontar del total de la línea.",
    )

    @api.onchange("discount_fixed")
    def _onchange_discount_fixed(self):
        """
        Cuando el usuario cambia el monto fijo, calculamos el porcentaje
        equivalente para que Odoo haga su magia estándar.
        """
        for line in self:
            if line.discount_fixed != 0:
                total_base = line.price_unit * line.product_uom_qty

                if total_base != 0:
                    # Fórmula: (Monto Fijo / Total Base) * 100
                    new_discount_percent = (line.discount_fixed / total_base) * 100
                    line.discount = new_discount_percent
            else:
                line.discount = 0

    @api.onchange("discount")
    def _onchange_discount(self):
        """
        Sincronización inversa: Si el usuario edita el porcentaje a mano,
        actualizamos el campo de monto fijo para que coincidan visualmente.
        """
        for line in self:
            total_base = line.price_unit * line.product_uom_qty
            # Fórmula: Total Base * (Porcentaje / 100)
            line.discount_fixed = total_base * (line.discount / 100)

    @api.onchange("product_uom_qty", "price_unit")
    def _onchange_quantity_price(self):
        """
        Si cambian la cantidad o el precio unitario, mantenemos el PORCENTAJE
        fijo (comportamiento estándar de Odoo) y recalculamos el monto fijo visual.
        """
        for line in self:
            total_base = line.price_unit * line.product_uom_qty
            line.discount_fixed = total_base * (line.discount / 100)
