{
    'name': 'PLE Registro de Inventario Permanente Valorizado 13.1',
    'version': '18.0.2.1.0',
    'author': 'Empiria',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Reporte SUNAT Formato 13.1 - Inventario Permanente Valorizado',
    'depends': [
        'ple_diary_book',
        'stock_account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/ple_report_stock_valued_inventory_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
