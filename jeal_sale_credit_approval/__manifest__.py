# -*- coding: utf-8 -*-
{
    'name': "Límite de crédito y aprobación de ventas al crédito",
    'summary': "Bloquea la confirmación de ventas al crédito que exceden la "
               "línea o tienen deuda vencida, con aprobación por correo.",
    'description': """
Límite de crédito y aprobación de ventas al crédito
===========================================================

Controla que ninguna venta al crédito se confirme si el cliente supera su
línea de crédito o tiene deuda vencida, salvo aprobación expresa del aprobador
desde su correo (botones Aprobar / Rechazar, enlace de un solo uso de 72 h).

Incluye:
  * Campo Contado / Crédito en la cotización.
  * Límite de crédito por cliente (en soles) con historial y permisos.
  * Cálculo de deuda total multimoneda y deuda vencida.
  * Bloqueo de confirmación + flujo de aprobación por correo.
  * Reenvío de solicitud vencida y rechazo con motivo obligatorio.
  * Re-aprobación cuando sube el importe.
  * Reportes de línea de crédito y de solicitudes de aprobación.
""",
    'author': "Empiria",
    'website': "https://www.empiria.pe",
    'category': 'Sales/Sales',
    'version': '18.0.1.4.2',
    'license': 'OPL-1',
    'depends': ['sale', 'account', 'stock', 'mail'],
    'data': [
        'security/credit_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/mail_templates.xml',
        'data/ir_cron.xml',
        'wizard/credit_limit_wizard_views.xml',
        'wizard/credit_approval_send_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/credit_approval_request_views.xml',
        'views/credit_public_templates.xml',
        'reports/credit_report_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
