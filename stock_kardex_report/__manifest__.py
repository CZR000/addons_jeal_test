{
    "name": "Stock Kardex Report",
    "version": "18.0.3.0.0",
    "author": "AlexJimmy159",
    "maintainer": "AlexJimmy159",
    "support": "AlexJimmy159@gmail.com",
    "website": "https://github.com/AlexJimmy159",
    "summary": "Kardex report for stock moves with cost details",
    "description": """
This module provides a comprehensive Kardex report for stock moves, including detailed cost information. 
It allows users to analyze inventory movements and their associated costs effectively, aiding in better 
inventory management and financial analysis.
""",
    "category": "Inventory/Inventory",
    "depends": [
        "stock_account",
        "account_reports",
        "stock_moves_history_fields",
        "stock_product_cost_change_log",
        "stock_date_effective",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_kardex_product_report.xml",
        "views/stock_kardex_location_report.xml",
        "views/menuitem.xml",
        "wizards/stock_kardex_cost_audit_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_kardex_report/static/src/js/stock_kardex_report.js",
            "stock_kardex_report/static/src/xml/stock_kardex_report.xml",
        ],
    },
    "module_type": "official",
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "Other proprietary",
}
