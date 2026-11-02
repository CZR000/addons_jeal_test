{
    'name': 'PLE Libro Mayor 6.1',
    'version': '18.0.3.3.2',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Reporte visual PLE Libro Mayor - Formato 6.1',
    'description': """
Reporte PLE Libro Mayor Formato 6.1
====================================
Genera un reporte Excel con el layout visual del Libro Mayor segun formato
6.1 de SUNAT, con cabecera de identificacion (Formato, Periodo, RUC, Razon
Social, Moneda) y detalle de movimientos agrupado por cuenta contable,
mostrando Saldo Anterior, Movimientos del periodo, Total Movimiento Cuenta
y Saldo Actual.
""",
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'depends': ['ple_diary_book'],
    'data': [
        'security/ir.model.access.csv',
        'views/ple_report_ledger_book_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
