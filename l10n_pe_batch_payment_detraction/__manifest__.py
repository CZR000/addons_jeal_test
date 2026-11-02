{
    'name': 'Detracción en Pago por Lotes',
    'version': '18.0.1.5.0',
    'category': 'Accounting/Localizations',
    'summary': 'Excluye pagos de detracción al crear el pago por lote',
    'author': 'Empiria',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'account_batch_payment',
    ],
    'data': [
        'views/account_payment_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
