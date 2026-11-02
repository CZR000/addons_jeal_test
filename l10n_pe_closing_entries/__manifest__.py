# -*- coding: utf-8 -*-
{
    "name": "Asientos de Cierre Contable",
    "version": "18.0.1.0.0",
    "summary": "Genera asientos de cierre por niveles, idempotentes y trazables.",
    "author": "SINETICS",
    "website": "https://www.sinetics.com",
    "category": "Accounting/Accounting",
    "license": "AGPL-3",
    "depends": [
        "account",
        "account_analytic_required",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/account_account_views.xml",
        "views/account_move_views.xml",
        "wizards/closing_entry_wizard_views.xml",
        "wizards/closing_entry_confirm_wizard_views.xml",
        "views/closing_entry_menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
