{
    "name": "Stock Moves History Fields",
    "version": "18.0.1.7.1",
    "author": "AlexJimmy159",
    "maintainer": "AlexJimmy159",
    "support": "AlexJimmy159@gmail.com",
    "website": "https://github.com/AlexJimmy159",
    "summary": "Adds additional fields to stock move lines for better tracking and historical data analysis",
    "description": """
This module adds additional fields to stock move lines to enhance tracking and historical data analysis.
""",
    "category": "Inventory/Inventory",
    "depends": [
        # Odoo community
        "stock_account",
        "product_hide_price_cost",
        "stock_date_effective",
    ],
    "data": [
        "security/security.xml",
        "views/stock_move_line_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_valuation_layer_views.xml",
    ],
    "module_type": "official",
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "Other proprietary",
}
