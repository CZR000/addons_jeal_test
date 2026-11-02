# -*- coding: utf-8 -*-
{
    'name': 'Balance de Comprobación Personalizado',
    'version': '18.0.1.0.2',
    'author': 'Empiria',
    'category': 'Accounting/Accounting',
    'summary': 'Balance de comprobación con saldo inicial desde diario de apertura',
    'depends': ['account_reports'],
    'data': [
        'views/res_config_settings_views.xml',
        'data/account_trial_balance_custom_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'account_trial_balance_custom/static/src/components/trial_balance_custom/filters.js',
            'account_trial_balance_custom/static/src/components/trial_balance_custom/filter_extra_options.xml',
            'account_trial_balance_custom/static/src/components/trial_balance_custom/filters.xml',
        ],
    },
    'license': 'LGPL-3',
    'auto_install': False,
    'installable': True,
}
