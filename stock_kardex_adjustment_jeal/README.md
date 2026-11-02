# Kardex valorizado con ajustes por línea (jeal)

Extiende `stock_kardex_report` según la nota técnica *Adaptación del módulo
stock_kardex_report: kardex valorizado por fecha contable con ajustes línea por
línea* (Connected Resources, enero 2026).

## Configuración (Inventario > Configuración > Ajustes > Ajustes del kardex valorizado)

| Parámetro | Connected |
|---|---|
| Diario de ajustes | Valoración del inventario (STJ); vacío = diario de inventario de la categoría |
| Cuenta de costo de ventas | 6912100 |
| Costo de devoluciones de clientes | Costo de la salida de origen |
| Umbral de tipo de cambio | 1.00 |
| Diarios de asientos manuales | ASIENTOS DE DESTINO (AED) |
| Cuentas excluidas | 2810000 |
| Crear capas de valoración | Sí |

La cuenta de valoración (20/24) y la 61 salen de la categoría del producto
(cuenta de valoración y cuenta de entrada de existencias). El tipo de
existencia (tabla 5) de los libros 12.1 y 13.1 se toma del producto o, si no
tiene, de la categoría (**Tipo de existencia (tabla 5)**, se hereda de la
categoría padre).

## Uso

Inventario > Informes > **Ajuste del kardex valorizado**: período, filtros y
parámetros (asientos manuales adicionales o excluidos, por ejemplo las
reclasificaciones RINV/2025/12/0005-0006 o las provisiones de tránsito).

1. **Calcular**: arma el kardex por fecha contable y muestra los ajustes y si
   están por crear, por actualizar o ya registrados. No registra nada.
2. **Registrar ajustes**: por cada ajuste crea un asiento (y el complementario
   contra la 61 en los de tipo de cambio) con la fecha del movimiento ajustado y
   una capa de revaluación vinculada. Si se vuelve a ejecutar, no duplica:
   actualiza los importes que cambiaron y revierte los que ya no aplican. Si
   alguna fecha está cerrada no registra nada y lista los pendientes.
3. **Exportar Excel**: hojas Kardex, Resumen por producto, Conciliación 20-24 y
   Kardex costos Odoo.
4. **Libros SUNAT** (pestaña del proceso): **Generar libro 13.1** y **Generar
   libro 12.1** crean el libro físico (Excel y PDF) y el TXT del PLE
   (`LE<RUC><AAAAMM>00130100001111.txt` / `…120100…`) con las mismas líneas del
   kardex. Solo con el mes completo, sin filtros y sin ajustes pendientes; antes
   vuelve a calcular. El 12.1 lleva solo las líneas con unidades. Al terminar
   muestra el saldo final del 13.1 contra el saldo contable por producto y las
   unidades del 12.1 contra el 13.1.

Si el cálculo no deja nada pendiente, el proceso queda en **Ajustes
registrados**.

Si la factura de una recepción en dólares está en otra orden de compra (OC
duplicada), indíquela en el campo **Factura para tipo de cambio** de la OC
(pestaña Otra información) o de la recepción.

## Reglas de valorización (nota de compras, devoluciones, fabricaciones y desmontajes)

El kardex recorre todos los productos juntos, por fecha contable. Dentro del
mismo día van primero las entradas (compras, reingresos, devoluciones de
clientes), luego la cadena de producción en el orden en que se hizo (cada
orden consume antes de producir, cada desmontaje saca el producto antes de
devolver los componentes) y al final las demás salidas (R11).

| Regla | Qué hace | Contrapartida |
|---|---|---|
| R1 | Devolución a proveedor al costo unitario de su recepción de origen (con diferencias de precio, costos en destino y ajustes). Si deja el producto sin saldo, se lleva todo el saldo | Cuenta de entrada de la categoría (61) |
| R2 | Reingreso al valor con que sale la devolución que revierte, aunque tenga fecha anterior | 61 |
| R3-R6 | Por cada factura (y nota de crédito o débito) de la línea de compra: facturado acumulado menos lo ya registrado (recepciones, devoluciones, diferencias de precio de Odoo aunque su asiento sea posterior o no tenga movimiento, y ajustes). Un ajuste por factura, sobre la recepción que quedó en el almacén, con la fecha de la factura (o de la recepción si la factura es anterior), separado en diferencia de cambio y de precio. Las notas de crédito y débito (07, 08) solo cambian el valor, salvo una nota de crédito que anula toda la factura. Los costos en destino cubren la diferencia de la factura; si son mayores (fletes) el exceso queda en el inventario. Después de una devolución, reingreso, recepción o costo en destino posterior a la factura, la compra se vuelve a cuadrar con lo facturado. Si se facturó más de lo recibido (tolerancia 0.1 %) no se ajusta y se marca para revisión | 6912100 y complementario contra la 61 |
| R7, R12 | Ajuste de costo de una salida | Venta (con orden de venta o con cliente en la guía) y sus devoluciones: 6912100. Si no, la cuenta del asiento del movimiento (producción, 61, etc.) |
| R8 | Los ajustes de los consumos de una orden pasan al producto fabricado | Cuenta de producción |
| R9 | Desmontaje de una orden: cada componente vuelve a su costo de consumo en la orden y el producto sale por esa suma (neutro) | Cuenta de producción |
| R10 | Con saldo negativo o en cero, la salida va al último costo promedio positivo y se marca para revisión. La entrada que cubre el negativo (también un saldo inicial negativo) lo regulariza a su costo, como el vacuum de Odoo | La de cada salida |

Los ajustes registrados se identifican por capa ajustada, tipo, factura y
fecha. Al reprocesar, un ajuste anterior se actualiza si cambia su importe o
su contrapartida, y se revierte si ya no aplica.

**Simulación**: en el proceso se puede calcular sin las correcciones manuales
(capas `kardex_cost_correction` o una lista de asientos) para comparar con lo
que propone el kardex. Una simulación no se puede registrar.

El proceso avisa (pestaña *Para revisar* y observaciones) de las líneas con
stock negativo, las compras con más cantidad facturada que recibida y los
consumos de órdenes o desmontajes sin capa de valoración, y compara el costo de
ventas del kardex con la 6912100 de los asientos de inventario y de ajustes. En
cada línea de ajuste se ve su contrapartida antes de registrar.

## Libros 13.1 y 12.1

| Campo | Movimientos | Ajustes y asientos manuales |
|---|---|---|
| CUO (2) | Número del asiento de inventario sin `/` ni `-` (igual que el libro diario) | Número del asiento de ajuste o manual |
| Correlativo (3) | Correlativo PLE del apunte de la cuenta 20/24 (`M…`); `A000000001` en el saldo inicial | Igual |
| Documento (10–13) | Documento de traslado del albarán; si no hay, el comprobante (serie-número PLE) o la guía | Tipo 00, serie = código del diario, número = resto del número del asiento |
| Tipo de operación (14) | Tabla 12 por las ubicaciones (16 en el saldo inicial) | 99 |
| Entradas / salidas | Cantidad, costo unitario (8 decimales) y total; salidas con cantidad y total negativos | Cantidad 0, costo unitario 0, importe en el costo total |

Los albaranes sin documento de traslado ni comprobante usan la referencia
interna y se listan en la validación para completarlos.

## Marca de los asientos

Cada asiento generado (y sus reversiones) lleva **Ajuste por kardex**, el
**Tipo de ajuste kardex** (Costo promedio, Tipo de cambio, Destino 61), el
proceso y la capa o el movimiento ajustado. En Asientos y Apuntes contables hay
columnas opcionales, filtros *Ajustes por kardex* / *Sin ajustes por kardex* y
agrupación por tipo. La actualización a 18.0.1.1.0 marca los asientos ya
registrados.

## Asientos

| Ajuste | Entrada | Salida |
|---|---|---|
| Costo de ventas | 20/24 a 6912100 | 6912100 a 20/24 |
| Tipo de cambio (a) | 20/24 a 6912100 | 6912100 a 20/24 |
| Tipo de cambio (b) | 6912100 a 61 | 61 a 6912100 |
