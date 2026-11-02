{
    'name': 'Stock Fix Compute Bulk Weight',
    'version': '18.0.1.0.0',
    'author': 'Leo Daniel FS',
    'company': 'Leo Daniel FS',
    'maintainer': 'Leo Daniel FS',
    'support': 'l30dfs@gmail.com',
    'website': 'https://www.linkedin.com/in/leo-daniel-flores',
    'summary': 'Fix compute bulk weight for delivery methods',
    'description': """
This module fixes the computation of bulk weight
for delivery methods in stock module.

Nota Odoo 18: el campo ``weight_bulk`` y el método ``_compute_bulk_weight``
se movieron del módulo ``delivery`` (v16) al núcleo ``stock`` (v18). Este
módulo sigue siendo necesario para reforzar el cómputo cuando hay productos
archivados o referencias colgantes en move lines.
""",
    'category': 'Inventory/Inventory',
    'depends': [
        # Odoo community
        'stock',
        'delivery',
    ],
    'application': False,
    'installable': True,
    'auto_install': False,
    'license': 'Other proprietary',
    'currency': 'USD',
    # Reference price
    'price': 10.00,
}
