{
    'name': 'MRP Workorder Early Consumption',
    'version': '18.0.1.3.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Consume los componentes y consumibles del centro de trabajo al terminar cada orden de trabajo.',
    'description': """
Consumo anticipado por orden de trabajo
=======================================
* Al terminar una orden de trabajo se consumen (movimientos de stock nativos)
  los componentes de la lista de materiales asignados a su operación.
* Consumibles por centro de trabajo: productos que no están en la lista de
  materiales y se gastan al operar (cantidad por unidad producida y/o fija
  por orden de trabajo). Se generan y consumen automáticamente al terminar.
* La valoración de esos consumos lleva la analítica del centro de trabajo.
* El costo del producto terminado incluye todo lo consumido anticipadamente.
""",
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'stock',
        'stock_account',
        'mrp_account',
        'mrp_workorder',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_workcenter_views.xml',
        'views/mrp_workorder_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
