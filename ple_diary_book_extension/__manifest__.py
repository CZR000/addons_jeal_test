# -*- coding: utf-8 -*-
{
    "name": "PLE Diario - Report Extension",
    "summary": "Extiende el reporte PLE Diario para incluir una versión Excel simplificada.",
    "description": """
        Módulo que extiende el modelo `ple.report.diary` para añadir una versión
        simplificada del reporte Excel, manteniendo sincronizados los datos binarios
        con el reporte original.
    """,
    "author": "SINETICS",
    "website": "https://www.sinetics.com",
    "category": "Accounting/Reporting",
    "version": "18.0.1.0.2",
    "license": "AGPL-3",
    "depends": [
        "ple_diary_book",
    ],
    "data": [
        "views/ple_report_diary_inh_views.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}