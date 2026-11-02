# -*- coding: utf-8 -*-
{
    "name": "Comisiones de venta - tipo de cambio venta",
    "version": "18.0.1.0.0",
    "category": "Sales/Commission",
    "summary": "Convierte los logros de comisiones con el tipo de cambio de venta",
    "description": """
Puente entre sale_commission_ext e invoice_purchase_exchange_rate: cuando la
compañía registra tipos de cambio de compra y de venta para la misma fecha, los
logros de comisiones (ventas) se convierten a la moneda del plan con el de venta.
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "OEEL-1",
    "depends": [
        "sale_commission_ext",
        "invoice_purchase_exchange_rate",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
