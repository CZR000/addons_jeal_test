{
    'name': 'Carrier Reference Number Extension',
    'version': '18.0.1.0.1',
    'summary': 'Autocompleta el campo Guía(s) de Remisión de la factura con las guías de los traslados de la venta',
    'description': """
Carrier Reference Number Extension
==================================

Extiende ``carrier_reference_number_invoice`` para que el campo
``carrier_ref_number`` de ``account.move`` se calcule automáticamente
a partir de las guías de remisión (``l10n_latam_document_number``) de
los traslados (``stock.picking``) asociados a las órdenes de venta
vinculadas a la factura.

- Ignora traslados en estado ``cancel``.
- Si la venta tiene varias facturas, cada factura muestra todas las
  guías de la venta (opción A).
- El campo sigue siendo editable manualmente, pero cualquier cambio
  posterior en los traslados (validación / cancelación / nueva guía)
  vuelve a recalcular el valor.
- Los números se concatenan separados por una coma seguida de un espacio.
""",
    'author': 'Empiria',
    'website': 'https://www.empiria.pe',
    'category': 'Accounting/Accounting',
    'license': 'LGPL-3',
    'depends': [
        'sale_stock',
        'l10n_pe_edi_stock',
        'carrier_reference_number_invoice',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
