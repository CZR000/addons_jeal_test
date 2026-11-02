# -*- coding: utf-8 -*-
{
    'name': 'HR Expense Extension',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Captura SUNAT en hr.expense y genera facturas de proveedor '
               'al aprobar el hr.expense.sheet.',
    'description': """
HR Expense Extension (Parte 1 — borrador)
=========================================

Extiende ``hr.expense`` para capturar información SUNAT (tipo de documento,
serie/número, asignación de IGV, categoría ECPN, comerciante, líneas del
comprobante) y, al aprobar el ``hr.expense.sheet``, genera facturas de
proveedor (``account.move`` tipo ``in_invoice``) válidas para el Registro
de Compras y compatibles con la localización PE.

Alcance de esta versión
------------------------
    * Captura de datos SUNAT en el gasto.
    * Generación de factura de proveedor por comprobante, tomando los
      importes ya calculados por el flujo nativo (respeta price_include).
    * Supresión del asiento nativo duplicado en sheets SUNAT.
    * Constraints de duplicidad y consistencia (sheets no mixtos).
    * Soporte de múltiples líneas por gasto (``hr.expense.line``).
    * Catálogos internos (IGV assignment, ECPN) autónomos.

Fuera de alcance (documentado)
------------------------------
    * Wizard de conciliación con anticipos → módulo separado
      ``hr_expense_account_conciliation``.
    * Multi-moneda en la factura generada — validación bloqueante si
      la moneda del gasto ≠ moneda de la compañía.
    * ``merchant_id`` es informativo — no cambia el partner del asiento
      ni de la factura.
    """,
    'author': 'Empiria S.A.C.',
    'website': 'https://www.empiria.pe',
    'license': 'LGPL-3',
    'depends': [
        'hr_expense',
        'account',
        'l10n_latam_invoice_document',
        'l10n_pe',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/l10n_pe_igv_assignment_data.xml',
        'views/l10n_pe_igv_assignment_views.xml',
        'views/l10n_pe_ecpn_category_views.xml',
        'views/hr_expense_views.xml',
        'views/hr_expense_sheet_views.xml',
        'views/account_journal_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
