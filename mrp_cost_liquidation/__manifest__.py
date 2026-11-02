{
    'name': 'MRP Liquidación de costos',
    'version': '18.0.1.3.4',
    'category': 'Manufacturing',
    'summary': """Reporte Liquidación de costos basado en Análisis de costos.""",
    'license': 'LGPL-3',
    'depends': [
        'mrp_account_enterprise',
        'mrp_landed_costs',
        # Odoo 18: el módulo `mrp_workorder_hr` fue eliminado en v17/v18.
        # Su sucesor en v18 es `mrp_workorder_hr_account`, que se autoinstala
        # cuando `mrp_workorder` y `mrp_account_enterprise` están presentes
        # (ambos ya están en nuestra cadena de dependencias).
        'mrp_workorder_hr_account',
    ],
    'data': [
        'views/mrp_production_views.xml',
        'views/mrp_cost_liquidation_report.xml',
        'views/mrp_cost_liquidation_views.xml',
        'views/account_move_views.xml',
        'views/mrp_workcenter_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
