# -*- coding: utf-8 -*-
{
    'name': 'Nota de Crédito - Tipo de Cambio Forzado',
    'version': '18.0.1.0.3',
    'summary': 'Hereda el tipo de cambio forzado de la factura original en notas de crédito',
    'description': """
        Este módulo extiende la funcionalidad de notas de crédito para que
        cuando se cree una nota de crédito desde una factura en moneda extranjera,
        se copie automáticamente el tipo de cambio forzado (to_force_exchange_rate)
        de la factura original.

        Esto asegura que la nota de crédito mantenga el mismo tipo de cambio
        que la factura a la cual se le aplica.
    """,
    'author': 'Tu Empresa',
    'category': 'Accounting/Accounting',
    'depends': [
        'account',
        'account_debit_note',
        # AUDITADO (migración TC forzado): este módulo escribe/lee
        # to_force_exchange_rate SIEMPRE en formato inverso, compatible con el
        # campo puente de account_field_to_force_exchange_rate (que traduce a
        # exchange_rate_type='forced' + exchange_rate). No requiere cambios.
        'account_exchange_currency',
        'account_field_to_force_exchange_rate',
    ],
    'data': [
        'views/account_move_reversal_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
