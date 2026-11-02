{
    "name": "Perú - Asientos De Destino",
    "version": "18.0.1.1.6",
    "author": "Odoo Company",
    "company": "Odoo Company",
    "maintainer": "Odoo Company",
    "summary": "Asientos de destino automáticos",
    "description": """
        Este módulo permite crear asientos de destino de forma automática.
    """,
    "category": "Accounting/Localizations",
    "depends": [
        "account",
        "analytic",
        "base_country_filter",
        "l10n_pe_journal_type",
        "invoice_type_document",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/account_account_views.xml",
        "views/account_analytic_account_views.xml",
        "views/account_group_views.xml",
        "views/account_move_views.xml",
        "views/account_journal_views.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "Other proprietary",
    # "post_init_hook": "_post_init_hook",
}
