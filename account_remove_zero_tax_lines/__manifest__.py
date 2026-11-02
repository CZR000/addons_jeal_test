# -*- coding: utf-8 -*-
{
    'name': 'Eliminar líneas de impuesto en cero al confirmar',
    'version': '18.0.1.0.1',
    'category': 'Accounting',
    'summary': 'Elimina automáticamente las líneas de impuesto con importe cero al confirmar la factura',
    'description': """
Cuando una factura tiene impuestos configurados al 0% (típicamente 0% Rta de 4TA),
Odoo genera una línea contable de impuesto con debit=0 y credit=0.
Este módulo muestra un aviso en borrador y elimina esas líneas automáticamente
al confirmar la factura, dejando registro en el chatter.
    """,
    'author': 'Empiria',
    'website': 'https://www.empiria.com.pe',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
