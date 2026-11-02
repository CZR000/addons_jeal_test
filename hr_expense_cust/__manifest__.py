{
    'name': 'Gastos - Personalización',
    'version': '18.0.1.0.0',
    'summary': 'Personalización del módulo de gastos: solicitud de desembolso, validaciones, aprobación automática de asientos',
    'description': """
        Módulo de personalización para el módulo de gastos:

        1. Diarios: habilitar cuentas por cobrar/pagar en método de pago del diario
        2. Gastos: nuevos campos (tipo de documento, proveedor, registro de compras)
        3. Gastos: validación de referencia de factura (8 dígitos después del guión)
        4. Gastos: al aprobar el informe se generan asientos automáticamente
        5. Solicitud de desembolso: menú en módulo de gastos con flujo de aprobación
    """,
    'category': 'Accounting/Expenses',
    'author': 'Empiria',
    'depends': [
        'hr_expense',
        'account',
        'mail',
        'l10n_latam_invoice_document',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_activity_type.xml',
        'wizard/disbursement_reject_wizard_views.xml',
        'views/account_journal_views.xml',
        'views/hr_expense_views.xml',
        'views/expense_disbursement_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
