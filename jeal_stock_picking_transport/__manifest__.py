# -*- coding: utf-8 -*-
{
    'name': 'JE-AL - Guía de Transportista (Picking y Compras)',
    'version': '18.0.5.2.0',
    'category': 'Inventory/Inventory',
    'summary': 'Agrega datos de transporte en recepciones y los vincula a órdenes de compra',
    'author': 'Empiria',
    'depends': [
        'stock', 
        'purchase'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
        'views/purchase_order_views.xml',
        'views/product_conversion_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
