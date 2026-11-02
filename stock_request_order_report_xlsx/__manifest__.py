# -*- coding: utf-8 -*-
{
    'license': 'LGPL-3',
    "name": "Reporte Pedidos de Existencia XLSX",
    "summary": """
        Reporte Pedidos de Existencia XLSX
    """,
    "description": """
        Reporte Pedidos de Existencia XLSX
    """,
    "author": "JEAL",
    "website": "https://www.jeal.com",
    "category": "",
    "version": "18.0.1.4.10",
    "depends": [
        "base",
        "report_xlsx",
        "stock_request",
        "stock_request_custom_field_permission",
    ],
    "data": [
        "views/report_stock_request_order.xml",
        "views/stock_request_order_inh_view.xml",
    ],
}
