# -*- coding: utf-8 -*-
{
    'license': 'LGPL-3',
    "name": "Agregar campos en la plantilla de orden de compra",
    "summary": """
        Agrega los campos: nombre completo, el RUC o DNI y sus cuentas de banco del proveedor en la plantilla de impresión en la orden de compra
    """,
    "description": """
        Agrega los campos: nombre completo, el RUC o DNI y sus cuentas de banco del proveedor en la plantilla de impresión en la orden de compra
    """,
    "author": "SINETICS",
    "website": "https://www.yourcompany.com",
    "category": "Uncategorized",
    "version": "18.0.0.0.2",
    "depends": [
        "account",
        "purchase",
    ],
    "data": [
        "report/purchase_order_templates.xml",
        "views/purchase_order_inh_view.xml",
        "views/res_partner_inh_view.xml",
    ],
}
