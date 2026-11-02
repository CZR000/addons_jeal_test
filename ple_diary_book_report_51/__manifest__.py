{
    'name': 'PLE Libro Diario 5.1',
    'version': '18.0.2.2.4',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Reporte visual PLE Libro Diario - Formato 5.1',
    'description': """
Reporte PLE Libro Diario Formato 5.1
=====================================
Genera un reporte Excel con el layout visual del Libro Diario segun formato
5.1 de SUNAT, con cabecera de identificacion (Formato, Periodo, RUC, Razon
Social, Moneda) y detalle de asientos contables agrupado por codigo de
subdiario (CL).

Configuracion:

* En cada Diario (account.journal) asignar el campo "Codigo Subdiario PLE"
  con el valor CL correspondiente (0 Apertura, 1 Caja, 2 Bancos,
  5 Registro de Compras, 13 Almacen/Inventarios, 14 Registro de Ventas,
  31 Planillas).
""",
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'depends': ['ple_diary_book'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_journal_views.xml',
        'views/ple_report_journal_book_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
