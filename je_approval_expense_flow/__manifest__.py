{
    'name': 'Aprobaciones - Puente a Gastos y Pagos',
    'version': '18.0.1.0.2',
    'summary': 'Vincula la app Aprobaciones con Gastos y Pagos a proveedores',
    'description': """
        Extiende la app Aprobaciones (approval.category / approval.request):

        1. Categorías: checkbox "Aplica a Informe de Gastos" y numeración
           automática configurable (padding de la secuencia).
        2. Categorías de tipo "Crear Pago a Proveedor": al aprobar la
           solicitud se abre el formulario de Pago a Proveedores prellenado.
        3. Correos automáticos (Acciones Automatizadas): al enviar la
           solicitud se notifica al aprobador; al confirmar el pago se
           notifica al solicitante.
        4. Menú "Solicitudes de Aprobacion" dentro de Gastos mostrando solo las
           categorías marcadas como de informe de gastos.
        5. Asiento generado desde un Informe de Gastos: detalle de cuenta 14
           y pagos pendientes de conciliar del empleado asociado.

        Los campos/validaciones al crear el gasto (referencia de factura,
        tipo de documento, registro de compras, política analítica, etc.) y
        la lógica de asiento que jala el proveedor viven en hr_expense_cust,
        no en este módulo - ambos son excluyentes, nunca conviven en la
        misma compañía.
    """,
    'category': 'Human Resources/Approvals',
    'author': 'Empiria',
    'depends': [
        'approvals',
        'account',
        'mail',
        'hr',
        'hr_expense',
        'base_automation',
        'l10n_pe_catalog',
        'account_move_protect',
    ],
    'data': [
        'views/approval_category_views.xml',
        'views/approval_request_views.xml',
        'views/account_payment_views.xml',
        'views/account_move_views.xml',
        'views/menu_views.xml',
        'data/mail_template_data.xml',
        'data/base_automation_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
