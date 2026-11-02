# -*- coding: utf-8 -*-
{
    'name': 'Account Asset - Valor Contable Restante',
    'version': '18.0.2.0.0',
    'category': 'Accounting',
    'summary': 'Muestra el valor contable restante (Valor Original - Depreciación Acumulada) en la tabla de depreciación de activos',
    'description': """
Agrega un campo calculado 'book_remaining_value' en las líneas de la tabla
de depreciación (account.move) que representa el valor contable restante
del activo considerando el valor original completo, de modo que:

- La primera fila arranca en Valor Original - Primera Depreciación
- La última fila termina exactamente en el Valor No Depreciable (salvage)

Reemplaza en la vista la columna nativa 'asset_remaining_value' que trabaja
sobre la base depreciable (original - salvage) y termina por debajo del residual.
    """,
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
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
