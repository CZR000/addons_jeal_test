{
    'name': 'Exchange Difference Analytic & Destination Entry',
    'version': '18.0.1.0.0',
    'author': 'Empiria',
    'summary': (
        'Configura una cuenta analítica por defecto por empresa para los asientos '
        'de diferencia de cambio y genera automáticamente el asiento de destino.'
    ),
    'depends': [
        'account',
        'analytic',
        'l10n_pe_destination_account',
    ],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'license': 'LGPL-3',
    'auto_install': False,
    'application': False,
    'installable': True,
}
