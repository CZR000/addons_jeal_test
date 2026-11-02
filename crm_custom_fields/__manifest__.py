# -*- coding: utf-8 -*-
{
    'name': 'CRM Custom Fields',
    'version': '18.0.1.0.2',
    'summary': 'Campos de categoría de pérdida y detalle para CRM',
    'description': """
        Módulo que reemplaza los campos creados con Studio para categoría de pérdida
        y detalle de producto/especificaciones en el CRM.
        - Agrega campos propios (sin depender de Studio)
        - Oculta los campos originales de Studio
        - Incluye campo consolidado para vista lista
    """,
    'author': 'EMPIRIA',
    'category': 'CRM',
    'depends': ['crm'],
    'data': [
        'views/crm_lead_form_view.xml',
        'views/crm_lead_list_view.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
