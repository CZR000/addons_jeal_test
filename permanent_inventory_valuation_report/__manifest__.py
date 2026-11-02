# -*- coding: utf-8 -*-
{
    'license': 'LGPL-3',
    "name": "Reporte Valorizado de Inventario Permanente",
    "summary": """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com
    """,
    "description": """
        Long description of module's purpose
    """,
    "author": "JEAL",
    "website": "https://www.jeal.com",
    "category": "",
    "version": "18.0.0.8.5",
    "depends": [
        "ple_sale_book",
        "purchase_stock",
        "sale_stock",
        "stock_account",
        "detail_report_internal_transfers",
        "l10n_pe_delivery_note_ple",
        "purchase_document_type_validation",
        "change_stock_and_account_move_date",
        "product_unspsc",
        "l10n_pe_edi",
        "tributary_address_extension",
        "invoice_type_document_extension",
        "ple_permanent_inventory_in_physical_units",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/update_opening_balances_view.xml",
        "views/stock_picking_inh_view.xml",
        "views/permanent_inventory_valuation_view.xml",
        "views/permanent_inventory_opening_balance_view.xml",
        "views/permanent_inventory_ending_balance_view.xml",
        "views/menuitems.xml",
    ],
}
