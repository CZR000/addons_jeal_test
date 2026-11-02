# -*- coding: utf-8 -*-
{
    "name": "Stock Accounting - Forzar Tipo de Cambio",
    "version": '18.0.1.1.3',
    "category": "Inventory/Inventory",
    "summary": "Control avanzado del tipo de cambio en recepciones y valoración contable de inventario.",
    "description": """
Gestión Avanzada del Tipo de Cambio en Valoración de Stock
==========================================================

Este módulo extiende el comportamiento estándar de Odoo para permitir un control
financiero estricto sobre el tipo de cambio aplicado en recepciones de mercancía
(compras internacionales) y su impacto en la contabilidad.

Principales funcionalidades:
----------------------------

* Fecha personalizada para el tipo de cambio:
  Permite seleccionar una fecha histórica para obtener la tasa del sistema.
  Ideal para casos donde la mercancía ingresa al almacén días después de
  la emisión de la factura comercial.

* Tipo de cambio forzado manualmente:
  Habilita la inserción de una tasa de cambio explícita y exacta, priorizándola
  sobre la tasa oficial del sistema. Es vital para registrar importaciones usando
  el tipo de cambio de los documentos aduaneros (ej. DUA/DAM).

* Consistencia contable integral:
  El asiento contable automático (account.move) generado por la recepción
  refleja exactamente el tipo de cambio configurado, evitando diferencias por
  redondeo en cuentas de puente o de variación cambiaria.

* Valoración real en el Kardex (SVL):
  Sobrescribe el cálculo nativo de las capas de valoración (stock.valuation.layer)
  para asegurar que el costo del producto en el inventario coincida de manera
  precisa con las reglas cambiarias establecidas por el usuario.
""",
    "author": "EMPIRIA",
    "website": "https://www.empiria.com",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "stock_account",
        "purchase_stock",
        "account_field_to_force_exchange_rate",
        "account_forced_exchange_rate_extended",
    ],
    "data": [
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
