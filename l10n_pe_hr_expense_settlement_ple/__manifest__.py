# -*- coding: utf-8 -*-
{
    "name": "Perú - Rendición de Gastos: Registro de Compras (PLE)",
    "version": "18.0.1.4.0",
    "category": "Human Resources/Expenses",
    "summary": "Tipos de comprobante, asignación de IGV y clasificación (tabla 30) de los gastos rendidos",
    "description": """
Puente entre l10n_pe_hr_expense_settlement y ple_purchase_book:

- En el gasto solo se ofrecen los tipos de comprobante asociados a los diarios de
  compras de la compañía (document_in_supplier_invoice), los mismos que acepta la
  factura.
- Categoría de gasto: "Asignación de IGV" (destino del IGV: gravadas, gravadas y no
  gravadas, no gravadas, sin IGV) que elige el impuesto de compra de la compañía con
  esa base imponible, y "Clasificación de bienes y servicios" (tabla 30) que llevan
  las facturas de compra generadas desde los gastos.
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "LGPL-3",
    "depends": [
        "l10n_pe_hr_expense_settlement",
        "ple_purchase_book",
    ],
    "data": [
        "views/product_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
