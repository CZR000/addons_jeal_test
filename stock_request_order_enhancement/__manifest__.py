# -*- coding: utf-8 -*-
{
    "name": "Stock Request Order Enhancements",
    "summary": "Extensión para mejorar la gestión de solicitudes de stock.",
    "description": """
        Este módulo extiende la funcionalidad de stock.request.order, 
        agregando nuevos campos y mejorando la búsqueda de productos.
    """,
    "author": "JEAL",
    "website": "https://www.jeal.com",
    "category": "Warehouse/Stock",
    "version": "18.0.0.2.4",
    "license": "LGPL-3",
    "depends": [
        "stock_request",
    ],
    "data": [
        "views/stock_request_order_inh_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
