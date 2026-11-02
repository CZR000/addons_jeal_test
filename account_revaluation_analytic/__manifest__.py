{
    'name': 'Revaluation Analytic Account',
    'version': '18.0.1.0.0',
    'author': 'Empiria',
    'summary': 'Agrega cuenta analítica al wizard de ganancias/pérdidas de moneda no realizadas',
    'depends': [
        'account_reports',
        'analytic',
    ],
    'data': [
        'views/multicurrency_revaluation_wizard_views.xml',
    ],
    'license': 'LGPL-3',
    'auto_install': False,
    'application': False,
    'installable': True,
}
