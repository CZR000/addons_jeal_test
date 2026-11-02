{
    'name': 'Perú - Mantener línea de impuesto con importe 0',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Conserva la línea contable del IGV aunque el importe neto sea 0 (requerido por PLE/SUNAT).',
    'description': """
Perú - Mantener línea de impuesto con importe 0
================================================

En Odoo 18 el motor de impuestos descarta la línea contable del impuesto
cuando el importe agrupado neto es 0 (por ejemplo, una factura con
Descuento +5,000 y Anticipo -5,000, ambos con IGV 18%).

En Perú, el PLE / Registro de Ventas requiere que esa línea exista
aunque el importe sea 0, para reflejar la cuenta de impuesto (p. ej. 4011100)
y sus tax_tag_ids (+S_TAX_OG) en el asiento.

Este módulo activa el flag interno `__keep_zero_line` de Odoo cuando la
compañía es peruana, lo que fuerza la creación de la línea con balance 0.
""",
    'depends': ['l10n_pe'],
    'author': 'Sinetics',
    'website': 'https://sinetics.com.pe',
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
}
