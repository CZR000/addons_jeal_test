# -*- coding: utf-8 -*-
{
    'name': 'Reportes: filtro y agrupación por plan raíz analítico',
    'version': '18.0.1.1.1',
    'category': 'Accounting/Accounting',
    'summary': 'Filtro "Planes raíz" con autoexpansión a cuentas y agrupación visual del header (plan raíz + subplan)',
    'description': """
Agrega un filtro "Planes raíz" al dropdown Analítica de los reportes financieros.
Al seleccionar uno o varios planes raíz, el sistema:

- Reemplaza las cuentas manuales por todas las cuentas cuyo root_plan_id
  esté en la selección.
- Muestra dos filas extra en el header:

    * Plan raíz (agrupa las cuentas por root_plan_id).
    * Subplan (agrupa las cuentas por su hijo directo del root;
      cuentas colgadas directo del root se colapsan bajo "—").

Alcance: vista web (Owl) + export PDF.
XLSX no incluido.
""",
    'depends': [
        'account_reports',
    ],
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'data': [
        'views/account_report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'report_analytic_root_plan/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}