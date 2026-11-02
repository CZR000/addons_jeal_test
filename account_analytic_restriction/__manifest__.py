# -*- coding: utf-8 -*-
{
    'name': 'Analytic Account - Restricción de Cuentas',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Restringe las cuentas contables permitidas por cuenta analítica',
    'author': 'Empiria',
    'depends': ['analytic', 'account'],
    'data': [
        'views/account_analytic_account_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
