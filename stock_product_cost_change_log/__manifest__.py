{
    "name": "Stock Product Cost Change Log",
    "version": "18.0.1.1.1",
    "author": "AlexJimmy159",
    "maintainer": "AlexJimmy159",
    "support": "AlexJimmy159@gmail.com",
    "website": "https://github.com/AlexJimmy159",
    "summary": "Log resulting unit cost in every stock valuation layer",
    "description": """
This module logs the resulting unit cost in every stock valuation layer created.
    """,
    "category": "Inventory/Inventory",
    "depends": [
        # Odoo community
        "stock_account",
        "product_hide_price_cost",
    ],
    "data": [
        "views/stock_valuation_layer_views.xml",
    ],
    "module_type": "official",
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "Other proprietary",
    "post_init_hook": "post_init_hook",
}
