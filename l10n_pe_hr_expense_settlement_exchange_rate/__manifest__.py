# -*- coding: utf-8 -*-
{
    "name": "Perú - Rendición de Gastos: tipo de cambio compra / venta",
    "version": "18.0.1.0.2",
    "category": "Human Resources/Expenses",
    "summary": "Tipo de cambio (compra o venta) de los cobros y pagos en moneda extranjera de la rendición",
    "description": """
Puente entre l10n_pe_hr_expense_settlement e invoice_purchase_exchange_rate:
los cobros (devolución del sobrante, "Liquidar saldo" a favor de la empresa) y
los pagos ("Liquidar saldo" a favor del empleado) en moneda extranjera que genera
la rendición usan el tipo de cambio configurado en la compañía. Por defecto:
cobros a TC compra y pagos a TC venta, como el banco.
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "LGPL-3",
    "depends": [
        "l10n_pe_hr_expense_settlement",
        "invoice_purchase_exchange_rate",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/account_payment_register_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
