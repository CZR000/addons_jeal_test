# Purchase Stock Price Difference Control

Corrige la inflación acumulativa del costo de inventario que se produce cuando una
factura de proveedor se pasa a borrador y se vuelve a publicar.

## El problema

Al publicar una factura de proveedor, `purchase_stock` compara el precio de la
factura con el de la capa de valorización de la recepción y, si difieren, crea una
capa de ajuste (`stock.valuation.layer` con `stock_valuation_layer_id` apuntando a
la capa de recepción).

El cálculo de la diferencia usa
`purchase_stock/models/stock_valuation_layer.py::_get_layer_price_unit()`, que
devuelve `layer.value / layer.quantity`, es decir el valor **original** de la
recepción. Ese valor nunca se modifica: los ajustes se registran como capas
aparte y sólo suman sobre `layer.remaining_value`.

La única defensa del core está en
`purchase_stock/models/account_invoice.py::_post()`:

```python
for invoice in self:
    if invoice.sudo().stock_valuation_layer_ids:
        continue
```

`account.move.stock_valuation_layer_ids` es el inverso de
`stock.valuation.layer.account_move_id`. Aunque `_prepare_pdiff_svl_vals()` crea la
capa con `account_move_id = <la factura>`, inmediatamente después
`_validate_accounting_entries()` crea el asiento de valorización (diario STJ) con
`'stock_valuation_layer_ids': [(6, None, [svl_id])]`, lo que **reasigna**
`account_move_id` a ese asiento. La condición, por tanto, nunca se cumple para una
factura de proveedor.

Resultado: cada ciclo borrador → publicar vuelve a calcular la misma diferencia
contra el valor original y la suma otra vez.

Caso real reportado (`[EQ] - Variador de frecuencia (Import) (110G/132P-4)`):

| Concepto                         | Importe      |
|----------------------------------|--------------|
| Recepción ANDAH/IN/03442         | S/    612.50 |
| Ajuste factura (1ª publicación)  | S/  6,635.58 |
| Ajuste factura (2ª publicación)  | S/  6,635.58 |
| Ajuste factura (3ª publicación)  | S/  6,635.58 |
| **Total valorizado por 1 unidad**| **S/ 20,519.24** |

## La solución

1. **En ejecución** — `account.move._post()` revierte los ajustes de la
   publicación anterior *antes* de que el core calcule el nuevo, generando una
   capa compensatoria de importe negativo (lo que pidió el usuario: «un ajuste
   negativo por el previo y pasar los ajustes correctos»). El valor final siempre
   es el de la última publicación, sin importar cuántas veces se repita el ciclo.
2. `button_draft()` y `button_cancel()` hacen lo mismo: una factura que no está
   publicada deja de valorizar el inventario.
3. **En el histórico** — el `post_init_hook` corrige automáticamente al instalar:
   - **Ajustes duplicados**: varios ajustes sobre la misma capa de recepción y la
     misma línea de factura; se conserva el último y se revierten los anteriores.
   - **Ajustes de facturas no publicadas**: siguen valorizando pese a que su
     factura fue cancelada o devuelta a borrador.

   La instalación **no corrige nada en línea**: activa el cron *Corregir ajustes
   de precio duplicados (histórico)*, que trabaja en lotes de 300, hace commit de
   cada lote y se desactiva solo al terminar. La corrección sigue siendo
   automática, pero la instalación termina en segundos.

   El cron hace dos fases por pasada: primero anula lo pendiente, y después
   **borra los pares ajuste+reversión cuya recepción sigue íntegra en almacén**,
   donde borrar y anular son equivalentes. Así no quedan líneas de más a la
   vista. Donde la mercadería ya salió, la anulación permanece: es la única
   forma de que la cuenta de existencias cuadre.

4. **Acción manual** — en *Valoración de stock*, seleccionando líneas:
   *Acciones → Eliminar valorización y regularizar asientos*. Borra el par
   entero (si se elige el ajuste, arrastra su reversión) y elimina sus asientos.
   Se niega, explicando por qué, cuando la mercadería ya salió del almacén.
5. **Bloqueo opcional** — ajuste por compañía en *Contabilidad → Configuración →
   Facturas de proveedor* para impedir que una factura ya valorizada vuelva a
   borrador. Desactivado por defecto; el grupo *Puede reiniciar a borrador
   facturas valorizadas* lo omite.

Las correcciones se registran siempre como capas negativas (nunca se borra nada),
de modo que la traza contable queda completa y
`stock_account` sigue calculando bien las salidas: tanto el AVCO como el FIFO leen
`candidate.value + sum(candidate.stock_valuation_layer_ids.mapped('value'))`.

### Mercadería ya consumida

Si la mercadería de la recepción ya salió del almacén, el exceso no está en el
inventario: la salida se lo llevó al costo de ventas. Devolverlo al inventario
dejaría el producto con valorización negativa y cantidad cero.

Por eso la reversión se reparte según `remaining_qty / quantity` de la capa de
recepción:

- la parte **en almacén** se devuelve al inventario con la capa negativa
  (`Dr existencias de compra / Cr inventario`);
- la parte **ya consumida** se corrige con un asiento aparte
  (`Dr existencias de compra / Cr costo de ventas`), referenciado en
  `pdiff_expense_move_id`, sin tocar el inventario.

Sobre los datos reales del staging (1.287 capas, S/ 34.328,49 de exceso) el
reparto es S/ 15.739,98 al inventario y S/ 18.588,51 al gasto, y ningún producto
queda con valorización negativa.

## Uso manual

*Inventario → Informes → Corregir ajustes de precio duplicados*: analiza primero
(sin modificar nada), muestra el detalle y permite corregir. La fecha de los
asientos de reversión es configurable para no tocar periodos cerrados.

Por RPC / shell:

```python
env['stock.valuation.layer'].action_pdiff_repair(limit=300)
```

Es idempotente: cuando devuelve `layers_to_reverse == 0` ya no queda nada.

## Nota: valorización de la recepción (asunto distinto)

En el caso del vídeo la recepción se valorizó en S/ 612.50 cuando la línea de
compra era de USD 2,107.00. La tasa de Odoo para esa fecha
(`res.currency.rate`, USD, 2026-05-12) es `0.29069767` (dólares por sol):

- correcto: `2107 / 0.29069767 = 7,248.08`
- registrado: `2107 * 0.29069767 = 612.50`

Es decir, la recepción aplicó el tipo de cambio **invertido**. La diferencia,
`7,248.08 - 612.50 = 6,635.58`, es exactamente el ajuste que la factura repitió
tres veces. Este módulo corrige la repetición; el origen de la inversión está en
la cadena `stock_account_forced_exchange_rate` / `exchange.rate.mixin` y se trata
por separado.

### Distribución analítica

Las líneas del asiento de corrección al gasto se marcan `display_type='cogs'` y
arrastran la `analytic_distribution` de la línea de factura de origen, igual que
hacen las líneas de corrección de precio del core (`_prepare_pdiff_aml_vals`).

Esto importa en esta base: `account_analytic_warning_wizard` exige distribución
analítica en las cuentas marcadas con *Usar Cuentas de Destino* (6560001, 6593000,
...) y exime justamente a las líneas `cogs`, que son las que Odoo genera de forma
automática en la valorización. Sin esa marca el asiento no se podía publicar y
abortaba toda la corrección.

Además cada asiento de corrección se publica dentro de un *savepoint*: si una
validación de un módulo de terceros lo rechaza, se registra en el log y en
`expense_failures` del resumen, pero no tumba el resto del lote.

## Rendimiento en bases grandes

Esta base tiene 148.113 capas de valorización y 1.900.944 apuntes contables. Dos
decisiones vienen de ahí, y ambas se tomaron después de que la instalación
tumbara el worker de odoo.sh:

- `pdiff_is_adjustment` **no se almacena**. Como campo calculado almacenado,
  Odoo lo recalcula fila por fila para todas las capas existentes durante la
  instalación, leyendo además `account.move.line`. Ahora se calcula al vuelo y
  las búsquedas usan `_search_pdiff_is_adjustment`.
- La detección de duplicados va en **SQL** (`_pdiff_find_duplicate_groups`,
  `_pdiff_find_unposted_adjustment_ids`, `_pdiff_count_pending`), no con
  `search()` + `filtered()`, que obligaba a cargar decenas de miles de registros
  y sus líneas de factura en memoria. Las consultas se apoyan en los índices de
  `stock_valuation_layer_id`, `account_move_line_id` y `pdiff_reversal_of_id`, y
  devuelven sólo ids, con `LIMIT` para acotar cada lote.

Los dos campos nuevos son columnas anulables con índice parcial: añadirlas no
reescribe la tabla.

## Pruebas

`odoo -d <db> -i purchase_stock_price_diff_control --test-enable --test-tags /purchase_stock_price_diff_control`

17 casos: ajuste único, no acumulación al re-publicar, cambio de precio entre
publicaciones, borrador/cancelación, balance de las reversiones, idempotencia,
asistente de limpieza, rutina de instalación, bloqueo de reinicio a borrador y
corrección contra el gasto cuando la mercadería ya salió del almacén.
