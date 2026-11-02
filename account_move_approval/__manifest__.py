# -*- coding: utf-8 -*-
{
    'name': 'Aprobación de Asientos Contables',
    'version': '18.0.5.0.2',
    'category': 'Accounting',
    'summary': 'Flujo de aprobación para asientos contables manuales',
    'description': """
Módulo de Aprobación de Asientos Contables
===========================================

Implementa un flujo de aprobación jerárquica para asientos contables:

* Flujo: Borrador → Pendiente de Aprobación → Publicado
* Configuración granular por diario contable
* Grupo de seguridad: Usuario aprobador
* Notificaciones automáticas vía actividades
* Trazabilidad completa (usuario, fecha, hora)
* Solo aplica a asientos manuales (tipo entry)

Características v2.0:

* Los aprobadores pueden publicar directamente sin flujo de aprobación
* Actividades se cierran correctamente con feedback
* Manejo robusto de errores durante la publicación post-aprobación
* Limpieza automática de campos al re-solicitar aprobación

Características v2.1:

* Los ajustes (write-offs) generados por el wizard de conciliación de
  Contabilidad (ej. redondeos) ya no bloquean la conciliación con un
  error sin salida: quedan pendientes de aprobación y la conciliación
  se completa automáticamente al aprobarse.
""",
    'author': 'Empiria S.A.C.',
    'license': 'LGPL-3',
    'depends': ['account', 'mail', 'account_accountant'],
    'data': [
        'security/account_move_approval_security.xml',
        'security/ir.model.access.csv',
        'data/mail_activity_type_data.xml',
        'wizard/account_move_reject_wizard_views.xml',
        'views/account_journal_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
