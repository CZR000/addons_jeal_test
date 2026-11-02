# -*- coding: utf-8 -*-
{
    'name': 'Reporte de Gastos Excel',
    'version': '18.0.3.0.1',
    'summary': 'Exportar líneas de asiento contable a Excel con filtros y campos dinámicos',
    'description': """
Módulo para exportar account.move.line a Excel.

Características:
================
* Dos modos de selección:
  - Usar registros seleccionados manualmente
  - Filtrar por rango de fechas (busca en TODOS los registros)
* Agregar campos adicionales dinámicamente al final del Excel
* Soporte para múltiples tipos de campos (texto, número, fecha, relaciones, etc.)
* Acceso desde Acción en lista de apuntes contables

Uso:
====
1. Ir a Contabilidad > Informes > Reporte de Gastos Excel
   O seleccionar líneas en apuntes contables y usar Acción
2. Elegir modo: Registros seleccionados o Rango de fechas
3. (Opcional) Agregar campos adicionales
4. Generar y descargar el Excel
    """,
    'category': 'Accounting',
    'author': 'Empiria S.A.C.',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'analytic',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/expense_report_wizard_views.xml',
    ],
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
