{
    'name': 'Liquidation Extensions',
    'version': '18.0.1.0.3',
    'summary': 'Payment state, invoice locking, and balance in liquidations',
    'depends': [
        'account_liquidation',
    ],
    'data': [
        'views/account_move_views.xml',
        'views/report_liquidation_views.xml',
        'views/report_liquidation_template_ext.xml',
    ],
    'license': 'LGPL-3',
    'auto_install': False,
    'application': False,
    'installable': True,
}
