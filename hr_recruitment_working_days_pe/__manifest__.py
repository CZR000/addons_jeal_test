# -*- coding: utf-8 -*-
{
    'name': 'Reclutamiento - Días Hábiles Perú',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Agrega métrica de días hábiles (Perú) al análisis de reclutamiento',
    'description': """
        Extiende el reporte de análisis de reclutamiento para incluir
        "Duración (días hábiles PE)", que cuenta los días laborables
        transcurridos entre la creación del candidato y la contratación,
        excluyendo sábados, domingos y feriados oficiales del Perú
        (incluyendo Jueves y Viernes Santo calculados dinámicamente).
    """,
    'author': 'Empiria S.A.C.',
    'license': 'LGPL-3',
    'depends': ['hr_recruitment_reports'],
    'data': [
        'views/hr_recruitment_report_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
