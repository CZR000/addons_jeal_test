{
    'name': 'Account Custom Extensions',
    'version': '18.0.1.0.1',
    'author': 'Empiria',
    'summary': 'Custom extensions for accounting: groupby analytic distribution and other modifications',
    'depends': [
        'account',
        'analytic',
        'l10n_pe_destination_account',
    ],
    'data': [
        'views/account_move_line_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'license': 'LGPL-3',
    'auto_install': False,
    'application': False,
    'installable': True,
}
