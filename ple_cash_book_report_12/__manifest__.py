{
    'name': 'PLE Libro de Caja y Bancos 1.2',
    'version': '18.0.2.1.2',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Reporte visual PLE Libro Caja y Bancos - Formato 1.2',
    'description': """
Reporte PLE Libro de Caja y Bancos - Formato 1.2
=================================================
Genera un reporte Excel con el layout visual del Libro de Caja y Bancos -
Detalle de los Movimientos de la Cuenta Corriente, segun formato 1.2 de
SUNAT.

Alcance
-------
Segmentado por mes dentro del rango de fechas. Por cada cuenta corriente
listada, muestra su SALDO ANTERIOR y luego una fila por cada CONTRAPARTIDA
de cada asiento que toque la cuenta. El saldo se calcula corriendo linea
por linea de contrapartida.

Filtro de cuentas (hardcoded, editar CASH_ACCOUNT_CODE_MIN / _PREFIX si
cambian)::

    code >= '1031002'  AND  code =like '10%'

Es decir, todas las cuentas del subgrupo 10 (Efectivo y equivalentes)
desde 1031002 en adelante, cubriendo el efectivo en transito no incluido
en el 1.1 y las cuentas corrientes en instituciones financieras (104x),
depositos (106x), etc.

Columnas
--------
* NUMERO REGISTRO: {CL}-{correlativo %08d} por (CL, YYYYMM). Un mismo
  asiento comparte un solo NUMERO REGISTRO en todas sus filas y en todas
  las secciones donde aparezca.
* FECHA OPERACION: account_move.date
* DESCRIPCION OPERACION: account_move.ref (fallback name)
* DOCUMENTO TRANSACCION (TD, NUMERO, FECHA): datos de la factura
  reconciliada con la LINEA CONTRAPARTIDA (no con la linea de caja).
  Fallback si no hay factura: OT + fecha DDMMYYYY + fecha del asiento.
* MON: MN para PEN, US para USD, primeras 2 letras para otras.
* CUENTA CONTABLE ASOCIADA (CODIGO, DENOMINACION): datos de la
  contrapartida.
* DEUDOR: contra.credit (cuando la contra se acredita, la cuenta se
  debita = entra plata)
* ACREEDOR: contra.debit (cuando la contra se debita, la cuenta se
  acredita = sale plata)
* SALDO: running de la cuenta corriente, actualizado por cada fila.

Sin bloques de cierre (TOTAL / SALDO ACTUAL) al final de cada seccion; el
reporte termina con la ultima linea de contrapartida.
""",
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'depends': ['ple_diary_book'],
    'data': [
        'security/ir.model.access.csv',
        'views/ple_report_cash_book_current_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
