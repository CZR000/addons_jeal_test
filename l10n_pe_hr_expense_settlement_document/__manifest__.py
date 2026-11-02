# -*- coding: utf-8 -*-
{
    "name": "Perú - Rendición de Gastos: comprobantes aceptados por proveedor",
    "version": "18.0.1.1.0",
    "category": "Human Resources/Expenses",
    "summary": "Aplica en el gasto los comprobantes aceptados según el tipo de identificación del proveedor",
    "description": """
Puente entre l10n_pe_hr_expense_settlement e invoice_validation_by_document:
en el gasto solo se ofrecen los tipos de comprobante que el tipo de
identificación del proveedor (RUC, DNI...) acepta; un tipo no aceptado se
rechaza al enviar el informe, indicando el gasto, en vez de fallar al publicar
la factura. Los comprobantes del diario fuera del Registro de Compras (gastos
sin sustento) no llevan tipo de documento: no se les aplica esa validación.
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "LGPL-3",
    "depends": [
        "l10n_pe_hr_expense_settlement",
        "invoice_validation_by_document",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
