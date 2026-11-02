# -*- coding: utf-8 -*-
{
    "name": "Anticipos y Revolventes",
    "version": "18.0.1.1.1",
    "category": "Accounting/Localizations",
    "summary": "Control de anticipos de clientes/proveedores y revolventes con "
               "documentos, saldos y conciliacion automatica",
    "description": """
Control de anticipos y revolventes
==================================
Convierte el seguimiento manual de anticipos y revolventes sobre las cuentas
de control en documentos con saldo propio (ANTC / REV) que se crean, aplican
y concilian automaticamente.

Ver documento de diseno: l10n_pe_advance_conciliation.
""",
    "author": "Empiria",
    "website": "https://empiria.pe",
    "license": "OPL-1",
    "depends": [
        "account",
        "accountant",
        "l10n_pe",
    ],
    "data": [
        "security/advance_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/advance_config_views.xml",
        "views/product_template_views.xml",
        "views/advance_views.xml",
        "views/account_move_views.xml",
        "wizards/advance_apply_wizard_views.xml",
        "wizards/advance_revolving_wizard_views.xml",
        "wizards/advance_close_wizard_views.xml",
        "wizards/advance_migration_wizard_views.xml",
        "wizards/advance_statement_wizard_views.xml",
        "report/advance_reconcile_report_views.xml",
        "report/advance_statement_report.xml",
        "report/advance_statement_templates.xml",
        "report/advance_statement_partner_templates.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
