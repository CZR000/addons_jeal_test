{
    "name": "Purchase Stock Price Difference Control",
    "version": "18.0.1.2.1",
    "summary": "Evita ajustes de valorizacion duplicados al reponer facturas de proveedor",
    "description": """
Control de ajustes de precio en la valorizacion de inventario
=============================================================

Cada vez que una factura de proveedor se pasa a borrador y se vuelve a publicar,
Odoo vuelve a calcular y a aplicar el ajuste por diferencia de precio sobre la
capa de valorizacion original (stock.valuation.layer), sin considerar el ajuste
aplicado por la publicacion anterior. El resultado es un costo inflado de forma
acumulativa.

Este modulo:

- Revierte el ajuste previo (asiento negativo) antes de aplicar el nuevo, de
  forma que el valor final siempre corresponde a la ultima publicacion.
- Mantiene el costo estandar del producto sincronizado con las capas vigentes.
- Permite bloquear (opcional, por compania) el reinicio a borrador de facturas
  de proveedor que ya generaron valorizacion.
- Corrige automaticamente el historico al instalarse (post_init_hook): revierte
  los ajustes duplicados dejando solo el ultimo valido, y retira los ajustes de
  facturas que ya no estan publicadas.
- Incluye un asistente para volver a analizar y corregir duplicados cuando haga
  falta.
""",
    "category": "Inventory/Purchase",
    "author": "Drayer Consulting",
    "website": "https://drayerconsulting.net",
    "depends": [
        "purchase_stock",
        "stock_account",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "data/server_actions.xml",
        "wizards/price_diff_cleanup_wizard_views.xml",
        "views/res_config_settings_views.xml",
        "views/stock_valuation_layer_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
