# -*- coding: utf-8 -*-
{
    'license': 'LGPL-3',
    "name": "l10n_pe_txt_reten",
    "summary": "Genera archivos TXT para la declaración de retenciones, integrándose con la contabilidad de Odoo.",
    "description": """
        Este módulo permite la generación de archivos en formato TXT para la declaración de retenciones, facilitando la integración con los sistemas contables y de cumplimiento normativo.
        Incluye herramientas para exportar datos de retenciones y genera reportes en formato compatible con las normativas locales.
    """,
    "author": "JEAL",
    "website": "https://www.jeal.com",
    "category": "Contabilidad",
    "version": "18.0.1.2.6",
    "depends": [
        "txt_retention_file_generator",
    ],
    "data": [
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
