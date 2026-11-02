{
    'name': 'Aprobación de Descuentos en Ventas',
    'version': '18.0.1.0.0',
    'summary': 'Aprobación de descuentos en cotizaciones por el Gerente de Ventas',
    'description': """
        Módulo para gestionar la aprobación de descuentos en cotizaciones de venta:

        - Campo "Gerente de Ventas" en usuarios para control de acceso a listas de precios
        - Solo el Gerente de Ventas puede crear/modificar/eliminar listas de precios
        - Configuración de niveles de descuento: sin autorización y con autorización
        - Flujo de aprobación automático cuando el descuento supera el límite configurado
        - Notificación automática al Gerente de Ventas mediante actividades en Odoo
        - Bloqueo de confirmación de pedido hasta obtener aprobación del descuento
        - Soporta descuento porcentual (%) y descuento fijo ($)
        - Botones de Aprobar / Rechazar en la cotización para el Gerente de Ventas
        - Trazabilidad completa: quién solicitó, quién aprobó/rechazó y cuándo
    """,
    'category': 'Sales/Sales',
    'author': 'Empiria',
    'depends': ['sale', 'mail', 'sales_team'],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_activity_type_data.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/sale_discount_reject_wizard_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
