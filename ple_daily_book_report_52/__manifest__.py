{
    'name': 'PLE Libro Diario Simplificado 5.2',
    'version': '18.0.4.2.7',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Reporte visual PLE Libro Diario Simplificado - Formato 5.2',
    'description': """
Reporte PLE Libro Diario Simplificado Formato 5.2
Genera un reporte Excel con el layout visual del Libro Diario Simplificado
segun formato 5.2 de SUNAT.
""",
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'depends': ['ple_diary_book'],
    'data': [
        'security/ir.model.access.csv',
        'views/ple_report_daily_book_simplified_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
