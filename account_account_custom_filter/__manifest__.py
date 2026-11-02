# -*- coding: utf-8 -*-
{
    "name": "Account Account Custom Filter",
    "version": "18.0.1.0.0",
    "author": "Empiria",
    "website": "https://empiria.pe",
    "license": "LGPL-3",
    "category": "Accounting/Accounting",
    "summary": "Filtro 'Con movimientos' en el plan contable",
    "description": """
Agrega un campo booleano computado (search-only) `has_movements` en account.account
y un filtro nativo "Con movimientos" en el search view del plan contable.

Útil para wizards que abren la vista de selección de cuentas (m2m) sobre el
catálogo completo — por ejemplo el reporte de Notas y Anexos — y quieren
restringir a cuentas que efectivamente tengan asientos posted.
    """,
    "depends": ["account"],
    "data": [
        "views/account_account_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
