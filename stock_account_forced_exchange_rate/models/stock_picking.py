# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "exchange.rate.mixin"]

    exchange_rate_date = fields.Date(
        string="Fecha del Tipo de Cambio",
        tracking=True,
        help="Establece una fecha específica para obtener el tipo de cambio del sistema. "
             "Si asignas un valor manual en 'Monto Forzado', esta fecha se limpiará. "
             "Es útil para alinear la valoración del inventario con la fecha original de la compra."
    )

    # ---------------------------------------------------------------------------- #
    #                                METODOS ONCHANGE                              #
    # ---------------------------------------------------------------------------- #

    @api.onchange("exchange_rate_date")
    def _onchange_exchange_rate_date(self):
        """
        Garantiza la exclusividad mutua: si se selecciona una fecha histórica,
        se elimina cualquier tasa manual forzada previamente ingresada.
        """
        # Limpiamos la tasa manual para obligar al mixin a usar la tasa del sistema en la fecha indicada.
        if self.exchange_rate_date and self.forced_exchange_rate:
            self.forced_exchange_rate = 0.0
    
    @api.onchange("forced_exchange_rate")
    def _onchange_forced_exchange_rate(self):
        """
        Garantiza la exclusividad mutua: si se ingresa una tasa de cambio manual,
        la fecha histórica pierde relevancia y se limpia.
        """
        # Prioriza el valor explícito del usuario sobre la fecha histórica.
        if self.forced_exchange_rate > 0 and self.exchange_rate_date:
            self.exchange_rate_date = False

    # ---------------------------------------------------------------------------- #
    #                  CONTRATO DEL MIXIN - TIPO DE CAMBIO                         #
    # ---------------------------------------------------------------------------- #

    def _get_exchange_rate_context(self):
        """
        Proporciona el contexto financiero necesario al mixin para calcular el tipo de cambio.
        
        :return: (Compañía, Moneda base, Moneda extranjera, Fecha de aplicación)
        :rtype: tuple(res.company, res.currency, res.currency, date)
        """
        self.ensure_one()
        company_currency = self.company_id.currency_id
        
        # Lectura segura: previene errores si el módulo "purchase_stock" no está instalado.
        purchase = getattr(self, 'purchase_id', False)
        foreign_currency = purchase.currency_id if purchase else company_currency
        
        # Aplica la fecha configurada o asume la fecha actual por defecto.
        date = self.exchange_rate_date or fields.Date.context_today(self)
        
        return self.company_id, company_currency, foreign_currency, date
    
    @api.model
    def _get_exchange_rate_depends(self):
        """
        Declara los campos que deben disparar el recálculo automático en el mixin.
        
        :return: Tupla con los nombres técnicos de los campos a observar.
        :rtype: tuple(str)
        """
        # Triggers estándar para recálculo financiero en el albarán.
        return (
            "company_id.currency_id",
            "purchase_id.currency_id",
            "exchange_rate_date",
        )

    def _get_default_exchange_rate_type(self):
        """
        Determina el tipo de conversión cambiaría basado en la naturaleza del movimiento.
        
        :return: El tipo de tasa a aplicar ('purchase', etc.).
        :rtype: str
        """
        self.ensure_one()
        
        # Fuerza el uso de la tasa de "Compra" si es una recepción de proveedores.
        if self.picking_type_code == 'incoming':
            return 'purchase'
            
        return super()._get_default_exchange_rate_type()