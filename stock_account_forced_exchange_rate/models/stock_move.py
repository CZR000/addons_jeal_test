# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_currency_convert_date(self):
        """
        Determina la fecha que se utilizará para la conversión de moneda.

        Si el movimiento proviene de una compra y el albarán (picking)
        tiene una fecha de tipo de cambio forzada, prioriza dicha fecha.

        :return: Fecha de conversión a aplicar.
        :rtype: date
        """
        self.ensure_one()

        # Prioriza la fecha manual del albarán si aplica al contexto de compra.
        if not self._should_ignore_pol_price() and self.picking_id.exchange_rate_date:
            return self.picking_id.exchange_rate_date

        return super()._get_currency_convert_date()

    def _get_price_unit(self):
        """
        Calcula el precio unitario de los productos en el movimiento de inventario.

        Intercepta el diccionario nativo de Odoo y, si el albarán tiene una tasa
        de cambio forzada, recalcula el valor revertiendo la conversión original
        y aplicando la tasa personalizada.

        :return: Diccionario mapeando {stock.lot: float(precio_unitario)}.
        :rtype: dict
        """
        self.ensure_one()
        # Retorna un diccionario {lote: precio_unitario}.
        prices_dict = super()._get_price_unit()

        # Evita procesar si no proviene de compra o no hay albarán.
        if self._should_ignore_pol_price() or not self.picking_id:
            return prices_dict

        picking = self.picking_id
        order = self.purchase_line_id.order_id
        company = order.company_id

        # Preserve native sale valuation unless a manual date/rate or the
        # automatic purchase-rate policy requires a conversion override.
        if (not picking.forced_exchange_rate and not picking.exchange_rate_date
                and not picking._uses_purchase_rate()):
            return prices_dict

        # Solo actúa si hay tasa forzada y las monedas son distintas.
        if not picking.exchange_rate or picking.exchange_rate <= 0 or order.currency_id == company.currency_id:
            return prices_dict

        conversion_date = self._get_currency_convert_date()
        new_prices_dict = {}

        # Recalcula el precio para cada lote devuelto por la función nativa.
        for lot, price_unit_origin in prices_dict.items():

            # Revierte el monto a la moneda origen de la compra.
            price_in_foreign = company.currency_id._convert(
                from_amount=price_unit_origin,
                to_currency=order.currency_id,
                company=company,
                date=conversion_date,
                round=False
            )

            # Aplica la tasa de cambio manual definida por el usuario.
            new_prices_dict[lot] = price_in_foreign * picking.exchange_rate

        return new_prices_dict

    def _generate_valuation_lines_data(self, partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description):
        """
        Genera los diccionarios con la información para la capa de valoración (SVL).

        Ajusta los importes en moneda extranjera (`amount_currency`) basándose en
        la tasa de cambio forzada del albarán, afectando las líneas de débito y crédito.

        :param partner_id: ID del proveedor (res.partner).
        :param qty: Cantidad del movimiento en la unidad de medida base.
        :param debit_value: Monto a debitar en moneda local.
        :param credit_value: Monto a acreditar en moneda local.
        :param debit_account_id: Cuenta contable de débito.
        :param credit_account_id: Cuenta contable de crédito.
        :param svl_id: ID de la capa de valoración (stock.valuation.layer).
        :param description: Descripción para el apunte contable.
        :return: Valores estructurados de las líneas contables.
        :rtype: dict
        """
        self.ensure_one()
        rslt = super()._generate_valuation_lines_data(
            partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description
        )

        picking = self.picking_id
        order = self.purchase_line_id.order_id

        # Verifica si aplican condiciones de multi-moneda y tasa forzada.
        if (not picking or not order
                or (not picking.forced_exchange_rate and not picking.exchange_rate_date
                and not picking._uses_purchase_rate())
                or picking.exchange_rate <= 0 or order.currency_id == self.company_id.currency_id):
            return rslt

        svl = self.env["stock.valuation.layer"].browse(svl_id)

        # Evita modificar capas que ya tienen un apunte contable generado.
        if not svl.account_move_line_id:
            foreign_currency = order.currency_id
            rate = picking.exchange_rate

            # Recalcula la moneda extranjera usando el balance local y la tasa forzada.
            rslt["credit_line_vals"]["amount_currency"] = foreign_currency.round(
                rslt["credit_line_vals"]["balance"] / rate
            )
            rslt["debit_line_vals"]["amount_currency"] = foreign_currency.round(
                rslt["debit_line_vals"]["balance"] / rate
            )

        return rslt
