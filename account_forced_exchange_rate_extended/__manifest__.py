{
    "name": "Account: Forced Exchange Rate Extended",
    "summary": "Tipo de cambio de la fecha y forzado en transacciones bancarias y su conciliación.",
    "description": """
Account: Forced Exchange Rate Extended
======================================
Muestra el tipo de cambio comercial de la fecha —el que la empresa carga desde
la SBS en ``res.currency.rate``— en las transacciones bancarias, y permite
forzar uno distinto para cuadrar la conciliación.

Convención de tasas
-------------------
``exchange_rate`` y ``forced_exchange_rate`` son tasas **comerciales**: cuántas
unidades de la moneda de la compañía equivalen a una unidad de la moneda
extranjera (3.7500 PEN por 1 USD).
El asiento contable sigue almacenando la tasa **inversa** en
``account.move.to_force_exchange_rate``, tal como lo espera
``account_field_to_force_exchange_rate``. El módulo traduce entre ambas
convenciones en un único punto (``_sync_forced_rate_to_move``).

Casuística
----------
* **Diario en moneda extranjera** (cuenta en USD, compañía en PEN): la tasa
  valoriza la propia transacción bancaria.
* **Diario en moneda de la compañía** (cobro en soles de una factura en
  dólares): la tasa valoriza los apuntes en moneda extranjera al conciliar, que
  es lo único que determina la diferencia de cambio.
* **Transacción con una tercera moneda** (``foreign_currency_id``): el campo se
  oculta, porque una sola tasa a nivel de asiento descuadraría esa pata.

Mixins reutilizables
--------------------
* ``exchange.rate.mixin`` — el par tipo de cambio de la fecha / forzado, para
  cualquier modelo con dos monedas.
* ``exchange.rate.reconcile.mixin`` — la diferencia de cambio calculada a una
  tasa forzada, para cualquier asistente de conciliación.
""",
    "author": "SINETICS",
    "website": "https://www.sinetics.com.pe",
    "category": "Accounting/Accounting",
    "version": '18.0.11.0.3',
    "license": "LGPL-3",
    "depends": [
        "account_accountant",
        "account_field_to_force_exchange_rate",
    ],
    "data": [
        "views/bank_rec_widget_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_forced_exchange_rate_extended/static/src/components/bank_reconciliation/kanban.js",
            "account_forced_exchange_rate_extended/static/src/components/bank_reconciliation/bank_rec_form.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
