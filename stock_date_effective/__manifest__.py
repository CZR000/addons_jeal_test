{
    'name': 'Stock Date Effective',
    'version': '18.0.2.2.7',
    'author': 'AlexJimmy159',
    'maintainer': 'AlexJimmy159',
    'support': 'AlexJimmy159@gmail.com',
    'website': 'https://github.com/AlexJimmy159',
    'summary': 'Editable effective date in picking',
    'description': """
This module activates the effective date so that it is editable in picking.
""",
    'category': 'Inventory/Inventory',
    'depends': [
        # Odoo community
        'purchase_stock',
    ],
    'data': [
        'security/security.xml',
        'views/stock_picking_views.xml',
        'views/stock_valuation_layer_views.xml',
        'views/stock_move_line_views.xml',
    ],
    'module_type': 'official',
    'application': False,
    'installable': True,
    'auto_install': False,
    'license': 'Other proprietary',
}
