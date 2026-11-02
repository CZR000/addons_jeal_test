# -*- coding: utf-8 -*-
{
    'name': 'Account Report - Ocultar Columnas en 0',
    'version': '18.0.1.4.0',
    'summary': 'Agrega la opcion "Ocultar columnas en 0" en los reportes dinamicos de contabilidad, analoga a "Ocultar lineas en 0".',
    'description': """
Account Report - Ocultar Columnas en 0

Agrega un nuevo filtro `filter_hide_0_columns` en `account.report` con los
mismos tres modos que el nativo `filter_hide_0_lines` (`by_default`,
`optional`, `never`).

Cuando esta activo, despues de que el motor calcula todas las lineas del
reporte se detectan las columnas cuyos valores son todos 0/None en todas las
lineas visibles y se eliminan de:

Util principalmente en reportes con columnas horizontales generadas
dinamicamente (por ejemplo, agrupaciones analiticas en el P&G peruano)
donde varias columnas quedan vacias segun el rango o filtros elegidos.
    """,
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'category': 'Accounting/Accounting',
    'depends': [
        'account_reports',
    ],
    'data': [
        'views/account_report_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'account_report_hide_columns/static/src/components/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
