{
    'name': 'Account Period Lock',
    'version': '18.0.1.0.0',
    'summary': 'Bloqueo contable por múltiples periodos mensuales',
    'description': """
        Extiende las "Fechas de cierre contable" para gestionar múltiples periodos de bloqueo:
        - Genera automáticamente los 12 periodos mensuales de un año
        - Filtra periodos por año (2025, 2026, etc.)
        - Bloquea o abre cada periodo de forma independiente
        - Valida automáticamente al crear/modificar asientos contables
    """,
    'category': 'Accounting/Accounting',
    'author': 'Empiria',
    'depends': ['account', 'account_accountant'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/account_period_lock_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
