{
    "name": "Stock Valuation Layer Account",
    "summary": "Shows the category stock valuation account on valuation layers "
               "(only for categories with automated valuation).",
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "author": "Empiria",
    "license": "LGPL-3",
    "depends": ["stock_account"],
    "data": [
        "views/stock_valuation_layer_views.xml",
        "data/ir_actions_server.xml",
    ],
    "installable": True,
    "application": False,
}
