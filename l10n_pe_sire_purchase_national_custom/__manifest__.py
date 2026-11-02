# -*- coding: utf-8 -*-
{
    "name": "Reporte RCE - Compras Nacionales Personalizado",
    "summary": "Personalización del Reporte RCE - Compras Nacionales para el SIRE en Perú.",
    "description": """
        Este módulo extiende las funcionalidades del módulo base "l10n_pe_sire_sunat" para incluir un reporte personalizado 
        del Registro de Compras Electrónico (RCE) enfocado en compras nacionales. Permite agregar detalles como cuentas 
        analíticas y códigos de cuentas contables relacionados con las líneas de movimiento contable.
    """,
    "author": "JEAL",
    "website": "https://www.jeal.com",
    "category": "Localization/Peru",
    "version": "18.0.4.2.1",
    "depends": [
        "account",
        "l10n_pe_sire_sunat",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/sire_purchase_national_custom_views.xml",
        "views/account_menuitem.xml",
    ],
}
