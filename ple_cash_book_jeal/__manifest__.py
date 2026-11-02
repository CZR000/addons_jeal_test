# -*- coding: utf-8 -*-
{
    "name": "PLE Libro Caja y Bancos 1.1 / 1.2 (jeal)",
    "version": "18.0.1.3.2",
    "category": "Accounting/Localizations/Reporting",
    "summary": "Libro Caja y Bancos SUNAT: efectivo (1.1) y cuentas corrientes (1.2) "
               "con banco del diario, medio de pago, girador y correlativo del Libro Diario",
    "description": """
Rehace la generación del PLE 1.1 y 1.2 de ple_cash_book (ple.report.cash.bank):

* 1.1 Efectivo: líneas de las cuentas marcadas "1.1" con los 19 campos SUNAT;
  documento relacionado y dato estructurado desde el comprobante conciliado.
* 1.2 Cuentas corrientes: solo cuentas de bancos; banco y cuenta bancaria del
  diario de banco de la cuenta. Si una cuenta "1.2" con movimientos no tiene
  banco, no se genera y se indica la cuenta.
* Medio de pago (tabla 1): por defecto desde el método de pago o el diario,
  copiado al asiento del pago o del extracto y editable; si falta, 003 y se avisa.
* Girador: socio del asiento, del extracto o de la única contrapartida.
* CUO y correlativo por línea, iguales al Libro Diario 5.1.
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "LGPL-3",
    "depends": [
        "ple_cash_book",
        "l10n_pe_edocument",
        "account_accountant",
    ],
    "data": [
        "views/account_journal_views.xml",
        "views/account_move_views.xml",
        "views/ple_report_cash_bank_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
