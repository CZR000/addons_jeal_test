{
    'name': 'PLE Registro Inventario Permanente Unidades Fisicas 12.1',
    'version': '18.0.2.1.2',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Reporte visual PLE Registro Inventario Permanente - Formato 12.1',
    'description': """
Reporte PLE Registro del Inventario Permanente en Unidades Fisicas 12.1
========================================================================
Genera un reporte Excel con el layout visual del "Registro del Inventario
Permanente en Unidades Fisicas - Detalle del Inventario Permanente en
Unidades Fisicas", segun formato 12.1 de SUNAT.

Alcance
-------
- Segmentado por mes dentro del rango de fechas.
- Un solo Excel con TODOS los productos almacenables (is_storable) que
  tengan al menos un movimiento en el mes; ordenados por product.name.
- Por cada producto: bloque de metadatos (codigo existencia, tipo T5,
  descripcion, codigo UM T6) + fila SALDO INICIAL + una fila por cada
  stock.move done, con saldo corriente en unidades fisicas.
- Movimientos interno-interno (transferencias entre almacenes) se
  descartan porque el reporte es a nivel compania y no cambian el saldo.

Cabecera comun por mes: Formato 12.1, Periodo, RUC, Razon Social,
Establecimiento (hardcoded '0000').

Mapeos
------
* TIPO (TABLA 10): via SUNAT_DOC_TYPE_MAP desde
  account.move.l10n_latam_document_type_id vinculado al stock.move
  (sale_line_id / purchase_line_id). Default '00' cuando no hay
  comprobante.
* TIPO DE OPERACION (TABLA 12): mapeado desde stock.picking.picking_type_id.code::

    incoming -> 02 (compra)
    outgoing -> 01 (venta)
    internal -> 05 (traslado)

  SALDO INICIAL siempre 16.
""",
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'depends': ['ple_diary_book', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/ple_report_stock_permanent_inventory_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
