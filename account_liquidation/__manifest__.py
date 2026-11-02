{
    'name': 'Liquidations',
    'version': '18.0.1.0.3',
    'depends': [
        'stock',
        'mail',
        'stock_picking_weighing',
        # TODO migration-audit: los dos módulos siguientes vienen de otros
        # bloques del cliente y aún no están migrados a v18.
        #   - l10n_pe_edi_stock: añade campo `l10n_latam_document_number` en
        #     stock.picking (lo usamos en operation_liquidation_line).
        #   - account_exchange_currency: añade campo `exchange_rate` en
        #     account.move (lo usamos en account_liquidation_line).
        # Si esos módulos renombran sus campos al migrar, hay que ajustar
        # los `related=` correspondientes.
        'l10n_pe_edi_stock',
        'account_exchange_currency',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_data.xml',
        'security/ir_rule.xml',
        'reports/report_liquidation_document_action.xml',
        'reports/report_liquidation_document_template.xml',
        'views/report_liquidation_views.xml',
        'views/stock_menus.xml',
    ],
    'auto_install': False,
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
