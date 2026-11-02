# -*- coding: utf-8 -*-
{
    "name": "Kardex valorizado con ajustes por línea (jeal)",
    "version": "18.0.1.2.8",
    "category": "Inventory/Inventory",
    "summary": "Kardex por fecha contable con ajuste al costo promedio debajo de cada "
               "salida y ajuste por tipo de cambio factura vs recepción, con capa de "
               "revaluación y asiento por línea",
    "description": """
Extiende stock_kardex_report con un proceso de ajuste del kardex por período:

* Orden por la fecha contable del asiento de cada capa de valoración.
* Cada salida al costo de Odoo y, debajo, el ajuste al último costo promedio
  (encadenado con todos los ajustes anteriores).
* Devoluciones de clientes al costo recalculado de la salida de origen o al
  promedio vigente.
* Ajuste por tipo de cambio factura vs recepción en las compras en moneda
  extranjera facturadas antes de validar la recepción, con enlace manual a la
  factura cuando está en otra orden de compra.
* Asientos manuales con producto en las cuentas de valoración (por ejemplo,
  ASIENTOS DE DESTINO) en el saldo inicial y en el mes.
* Una capa de revaluación y un asiento por línea de ajuste con la fecha del
  movimiento ajustado; reproceso sin duplicar (actualiza o revierte).
* Exportación a Excel: kardex con ajustes, resumen, conciliación contra las
  cuentas de valoración y kardex a costos de Odoo.
* Libros SUNAT 13.1 (valorizado) y 12.1 (unidades físicas) del kardex con
  ajustes: libro físico en Excel y PDF y TXT del PLE.
* Marca «Ajuste por kardex» y tipo de ajuste en los asientos y apuntes, con
  filtros y agrupación.
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "LGPL-3",
    "depends": [
        "stock_kardex_report",
        "purchase_stock",
        "sale_stock",
        "l10n_latam_invoice_document",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/purchase_order_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_kardex_adjustment_line_views.xml",
        "views/stock_kardex_adjustment_views.xml",
        "views/account_move_views.xml",
        "views/product_category_views.xml",
        "report/kardex_ple_report.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "external_dependencies": {"python": ["xlsxwriter"]},
    "installable": True,
    "application": False,
    "auto_install": False,
}
