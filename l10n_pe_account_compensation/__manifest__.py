# -*- coding: utf-8 -*-
{
    'name': 'Compensación de Cuentas',
    'version': '18.0.9.9.4',
    'author': 'Empiria',
    'website': 'https://www.empiria.com.pe',
    'category': 'Accounting/Localizations',
    'license': 'LGPL-3',
    'summary': 'Compensación automática de facturas de venta y compra del mismo socio',
    'description': """
Compensación de Cuentas por Cobrar y Pagar - Perú
==================================================
Permite compensar automáticamente facturas de cliente y proveedor
cuando el socio actúa como cliente y proveedor a la vez.

Funcionalidades:
    * Botón "Aplicar Compensación" en facturas de venta y compra
    * Wizard con precarga automática de facturas del tipo contrario
    * Generación automática de asiento contable en borrador
    * Conciliación automática al publicar el asiento
    * Manejo de diferencia cambiaria
    * Reverso de compensación con ruptura de conciliación
    """,
    'depends': [
        'account',
        'l10n_pe_edi',
    ],
    'data': [
        'security/compensation_groups.xml',
        'security/compensation_security.xml',
        'security/ir.model.access.csv',
        'wizards/compensation_wizard_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
