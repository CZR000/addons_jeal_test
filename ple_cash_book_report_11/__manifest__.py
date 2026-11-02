{
    'name': 'PLE Libro de Caja y Bancos 1.1',
    'version': '18.0.2.1.1',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Reporte visual PLE Libro Caja y Bancos - Formato 1.1',
    'description': """
Reporte PLE Libro de Caja y Bancos - Formato 1.1
=================================================
Genera un reporte Excel con el layout visual del Libro de Caja y Bancos -
Detalle de los Movimientos del Efectivo, segun formato 1.1 de SUNAT.
""",
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'depends': ['ple_diary_book'],
    'data': [
        'security/ir.model.access.csv',
        'views/ple_report_cash_book_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
