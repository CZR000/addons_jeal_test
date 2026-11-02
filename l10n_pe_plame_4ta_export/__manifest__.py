# -*- coding: utf-8 -*-
{
    'name': 'PLAME - Exportación 4ta Categoría (.ps4)',
    'version': '18.0.1.0.2',
    'category': 'Accounting/Localizations',
    'summary': 'Genera el archivo plano .ps4 para importación masiva en PDT PLAME (Recibos por Honorarios y Dietas)',
    'description': """
Módulo para exportar Recibos por Honorarios y Dietas de Directorio
en el formato oficial .ps4 requerido por el PDT PLAME de SUNAT.
Estructura oficial: Estructura 20 - Detalle de Comprobantes de 4ta Categoría.
    """,
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'l10n_pe',
        'l10n_pe_edi',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/plame_4ta_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
