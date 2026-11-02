{
    "name": "Product Hide Price and Cost",
    "version": "18.0.1.0.1",
    "author": "AlexJimmy159",
    "maintainer": "AlexJimmy159",
    "support": "AlexJimmy159@gmail.com",
    "website": "https://github.com/AlexJimmy159",
    "summary": "Hide product price and cost based on user groups",
    "description": """
This module allows you to hide product prices and costs based on user groups.
You can configure which user groups can see the product prices and costs,
enhancing the security and confidentiality of sensitive pricing information.
""",
    "category": "Inventory/Inventory",
    "depends": [
        # Odoo community
        "product",
    ],
    "data": [
        "security/security.xml",
        "views/product_product_views.xml",
        "views/product_template_views.xml",
    ],
    "module_type": "official",
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "Other proprietary",
}
