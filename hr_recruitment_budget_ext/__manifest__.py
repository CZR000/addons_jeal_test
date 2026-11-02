{
    'name': 'Reclutamiento y Presupuesto - Extensiones',
    'version': '18.0.1.0.0',
    'author': 'Empiria',
    'summary': (
        'Control de permiso para crear empleados desde reclutamiento '
        'y alertas de exceso de presupuesto en asientos contables'
    ),
    'depends': [
        'hr_recruitment',
        'account_budget',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/budget_warning_wizard_views.xml',
        'views/res_users_views.xml',
        'views/hr_applicant_views.xml',
        'views/hr_candidate_views.xml',
    ],
    'license': 'LGPL-3',
    'auto_install': False,
    'application': False,
    'installable': True,
}
