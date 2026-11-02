# Account: Forced Exchange Rate Extended

Muestra el tipo de cambio de la fecha —el que la empresa carga desde la SBS en
`res.currency.rate`— en las transacciones bancarias, y permite forzar otro para
cuadrar la conciliación.

## Convención

Todas las tasas del módulo son **comerciales**: unidades de moneda de compañía
por una de la extranjera (`3.7500` PEN por 1 USD).

`account.move.to_force_exchange_rate` usa la **inversa** (`0.266666`). El módulo
traduce entre ambas en un solo punto: `_sync_forced_rate_to_move()`.

## Casuística

`exchange_rate_case` clasifica cada transacción; de ahí salen la visibilidad del
campo y el punto donde se aplica la tasa.

| Diario | 3ª moneda | Caso | Dónde aplica |
|---|---|---|---|
| = compañía | no | `counterpart` | diferencia de cambio al conciliar |
| ≠ compañía | no | `liquidity` | pata bancaria del asiento |
| cualquiera | sí | `none` | no aplica, el campo se oculta |

**`counterpart`** — cobras en soles una factura en dólares. La transacción no
tiene nada que convertir; el T.C. entra al conciliar, cuando Odoo valoriza el
apunte en dólares. Se resuelve en
`_lines_get_account_balance_exchange_diff()`.

**`liquidity`** — cuenta bancaria en dólares, compañía en soles. Se resuelve en
`_prepare_move_line_default_vals()`, único punto donde Odoo convierte el importe
del diario a moneda de compañía. Al sobrescribirlo, la tasa llega sola al saldo
abierto, la diferencia de cambio, los impuestos y la conciliación parcial.

**`none`** — la tasa del asiento se aplica a todas las líneas en moneda
extranjera, así que forzarla revalorizaría también la tercera moneda y
descuadraría el asiento. Por lo mismo, conciliar apuntes en dos monedas
extranjeras distintas bajo una sola tasa lanza `UserError` al validar.

## Mixins reutilizables

### `exchange.rate.mixin`

T.C. de la fecha + forzado para cualquier modelo con dos monedas.

```python
class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "exchange.rate.mixin"]

    def _get_exchange_rate_context(self):
        self.ensure_one()
        return self.company_id, self.company_id.currency_id, self.currency_id, self.date_order

    @api.model
    def _get_exchange_rate_depends(self):
        return ("company_id", "currency_id", "date_order")
```

Aporta `exchange_rate`, `forced_exchange_rate` y `exchange_rate_case`, más
`_get_market_exchange_rate()`, `_get_effective_exchange_rate()`,
`_convert_to_company_currency()` y `_get_inverse_exchange_rate()`.

### `exchange.rate.reconcile.mixin`

Diferencia de cambio a tasa forzada, para cualquier asistente de conciliación.

```python
class BankRecWidget(models.Model):
    _name = "bank.rec.widget"
    _inherit = ["bank.rec.widget", "exchange.rate.reconcile.mixin"]

    def _get_exchange_rate_source(self):
        self.ensure_one()
        return self.st_line_id
```

## Tipo de cambio SBS: compra o venta

`exchange_rate_type` (Compra / Venta) decide con qué tasa de la fecha se
valoriza la operación. Por defecto propone **compra** para lo que ingresa y
**venta** para lo que sale, criterio SUNAT; el contador puede cambiarlo en el
widget y su elección sobrevive a cambios de importe o fecha.

`forced_exchange_rate` sigue por encima: sobrescribe lo que la fecha y el tipo
hayan traído, para cuadrar diferencias de milésimas.

### Integración con el módulo de carga de tasas

Ese módulo guarda dos filas por día en `res.currency.rate`, marcadas con su
campo `exchange_rate` (`sale` / `purchase`), y deja la **venta** como tasa por
defecto de Odoo sobrescribiendo la consulta de `res.currency`. La compra la
expone aparte:

```python
res.currency._get_conversion_purchase_rate(from_currency, to_currency, company, date)
```

Este módulo lee así:

* **venta** → conversión estándar de Odoo, que ya devuelve la de venta;
* **compra** → el método de arriba, si existe.

Mientras ese módulo no esté instalado, `_uses_purchase_rate()` devuelve `False`
y todo cae en la conversión estándar: el campo se puede elegir pero no altera
ningún importe. En cuanto exista, `_overrides_odoo_rate()` se activa y la
compra revaloriza el asiento sin necesidad de forzar nada.

### Aviso sobre el diseño de ese módulo

Dos cosas a resolver ahí antes de darlo por terminado:

1. `res.currency.rate` tiene `unique (name, currency_id, company_id)`
   (`base/models/res_currency.py`). Guardar compra y venta el mismo día exige
   eliminar esa restricción.
2. En Odoo 18 **no existe** `_get_query_rates`; la consulta se arma dentro de
   `res.currency._get_rates` con `_search` y `SQL()`, no con SQL plano. El
   override tendrá que reescribir `_get_rates` o introducir ese gancho.

## Estructura

Cada archivo replica la ruta del estándar que extiende.

| Este módulo | Extiende |
|---|---|
| `models/account_bank_statement_line.py` | `account/models/…` |
| `models/bank_rec_widget.py` · `bank_rec_widget_line.py` | `account_accountant/models/…` |
| `views/bank_rec_widget_views.xml` | `account_accountant/views/…` |
| `static/src/components/bank_reconciliation/kanban.js` · `bank_rec_form.xml` | `account_accountant/static/src/components/bank_reconciliation/…` |

Los dos `*_mixin.py` no extienden nada: son aportes propios.

## Dónde se edita la tasa

| Punto de entrada | OWL |
|---|---|
| Botón **Nuevo** del widget | no |
| Diálogo **Añadir una transacción** | no |
| Panel **Operaciones manuales** al conciliar | sí |
| Columnas opcionales de la lista de transacciones | no |

En el panel, editar la tasa en el caso `counterpart` **no reconstruye el
widget**: recalcula la diferencia de cambio y el saldo abierto conservando los
apuntes ya montados. En `liquidity` sí, porque cambia todo el asiento.

## El céntimo de desfase contra facturas

La pata bancaria vale siempre **`importe x tasa`**, el mismo número que da la
calculadora: 88,500.44 × 3.356 = 297,007.48.

La factura suele estar contabilizada a otro valor —297,007.46— porque
`account.move` convierte y **redondea línea a línea** y luego suma, mientras que
el extracto convierte el total de una vez. Esos dos céntimos se asientan como
**diferencia de cambio**, que es lo que son, y el asiento cierra sin saldo
abierto.

No se absorben en el banco. Hacerlo cuadraría el asiento con dos líneas, pero
dejaría la cuenta bancaria valorizada en 297,007.46, contradiciendo lo que el
contador calcula a mano. El origen del desfase está en el redondeo de la
factura, no en la conciliación.

## Trampas del estándar que este módulo evita

**`FloatField` en el panel.** `account_bank_statement_import` define
`BankRecKanbanUploadController`, que copia el mapa `components` de su padre al
cargarse y re-registra la vista con `force: true`. Parchear la clase padre no
alcanza; se parchea el controlador registrado y se escucha el evento `UPDATE`.

**Dependencias en `bank.rec.widget.line`.** Ese modelo no tiene tabla
(`_table_query = "0"`). Una dependencia como `wizard_id.st_line_id.exchange_rate`
hace que el ORM emita `SELECT ... FROM (0)` al escribir cualquier línea de
extracto y rompe su creación. Todos los `@api.depends` de ese archivo se limitan
a `("flag", "wizard_id")`.

**Escritura sin cambio.** Escribir la misma tasa haría que
`_synchronize_to_moves` reconstruya el asiento igualmente, y en una transacción
conciliada eso borra sus contrapartidas. `write()` descarta la clave cuando el
valor no cambió.

## Advertencias operativas

Editar la tasa en el panel **escribe en base** aunque no valides: es el
comportamiento nativo de Odoo para ese panel.

`exchange_rate` es almacenado. Si corriges una tasa SBS de una fecha ya usada,
las transacciones de esa fecha quedan desactualizadas:

```python
lines = env['account.bank.statement.line'].search([('date', '=', fecha)])
lines.modified(['date'])
lines.flush_recordset()
```

## Migración desde 18.0.2.0.0

`migrations/18.0.3.0.0/post-migration.py` convierte la columna heredada
`to_force_exchange_rate` (inversa) al nuevo `forced_exchange_rate` (comercial).
La columna antigua se conserva; una vez validada puede eliminarse con
`ALTER TABLE account_bank_statement_line DROP COLUMN to_force_exchange_rate;`.

## Pruebas

```bash
odoo-bin -d <bd> -u account_forced_exchange_rate_extended \
     --test-enable --test-tags /account_forced_exchange_rate_extended
```

| Clase | Cubre |
|---|---|
| `TestExchangeRateCase` | clasificación de los tres casos |
| `TestExchangeRateResolution` | oficial, forzada, fecha, inversa, redondeo |
| `TestLiquidityValuation` | asiento de la transacción |
| `TestCounterpartValuation` | diferencia de cambio al conciliar |
| `TestWidgetFields` | lo que se ve en el panel |
| `TestExchangeRateType` | compra/venta, valorización y respaldo sin el módulo SBS |
| `TestRoundingGap` | el céntimo de la factura va a diferencia de cambio |
| `TestGuards` | conciliadas, negativas, dos monedas, cuentas faltantes |

## Deuda pendiente (otro módulo)

`account_field_to_force_exchange_rate` usa `to_force_exchange_rate` con dos
convenciones opuestas: inversa en `account_move.py` y
`account_move_line.py`, comercial en `account_payment.py::_prepare_move_line_default_vals`.
Eso produce importes erróneos en pagos en moneda extranjera. Unificar en
`account_payment.py` usando `1 / to_force_exchange_rate`, con test de regresión.
