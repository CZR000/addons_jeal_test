{
    'name': 'Format SIRE SUNAT (Book Sale) Correction',
    'version': '18.0.2.0.1',
    'author': 'Ganemo',
    'website': 'https://www.ganemo.co',
    'category': 'Accounting/Localizations',
    'depends': [
        # TODO migration-audit: l10n_pe_sire_sunat viene de otro bloque del
        # cliente y aún no está migrado a v18. Este módulo hereda de
        # `sire.sale.base` y sobrescribe `_select_sire_sale` y
        # `_process_query_results`. La firma de esos métodos en upstream v18
        # se mantiene; si cambia, hay que ajustar este override.
        'l10n_pe_sire_sunat',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'Other proprietary',
}
