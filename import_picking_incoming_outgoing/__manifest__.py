# -*- coding: utf-8 -*-
{
    'name': 'Importar Transferencias de Inventario (Recepciones / Entregas / Transferencias Internas)',
    'version': '18.0.24.0.0',
    'category': 'Inventario/Almacén',
    'summary': 'Importar transferencias de inventario desde archivos Excel (.xls/.xlsx)',
    'description': """
        Este módulo permite importar transferencias de inventario desde archivos Excel.
        Soporta:
        - Recepciones (Incoming Shipments)
        - Entregas (Delivery Orders)
        - Transferencias Internas (Internal Transfers)

        Opciones de búsqueda de productos:
        - Por Nombre
        - Por Referencia Interna (Código)
        - Por Código de Barras

        Soporta trazabilidad por Lote y Número de Serie.
        Agrupa automáticamente por propietario.
    """,
    'author': 'Empiria S.A.C.',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        # TODO migration-audit: los 3 módulos siguientes vienen de otros
        # bloques del cliente y aún no están migrados a v18. Este módulo
        # detecta dinámicamente si los campos existen (`if 'transportista_id'
        # in picking_fields:`), por lo que si los nombres cambian en la
        # migración del bloque correspondiente habrá que ajustar aquí.
        'jeal_stock_picking_transport',
        'invoice_type_document_extension',
        'l10n_pe_edi_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/importar_transferencia_view.xml',
    ],
    'external_dependencies': {
        'python': ['xlrd'],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
