{
    'name': 'Activos - Factura Obligatoria',
    'version': '18.0.2.0.0',
    'summary': 'Hace obligatorio registrar al menos una factura en el activo',
    'description': """
Activos - Factura Obligatoria
=============================

Este módulo valida que todo activo (account.asset) tenga registrada al menos
una línea en la pestaña "Facturas" antes de poder guardarse.

Comportamiento:
    * La validación se dispara en cualquier estado (borrador, en proceso, etc.).
    * Se excluyen los modelos de activo (state = 'model'), ya que por
      definición no se asocian a una factura.
    * Los activos auto-generados desde una factura de proveedor pasan la
      validación de forma natural, ya que se crean con la línea asociada.
    """,
    'author': 'Empiria',
    'website': 'https://empiria.pe',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'depends': [
        'account_asset',
    ],
    'data': [
        'views/account_asset_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
