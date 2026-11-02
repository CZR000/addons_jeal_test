# Perú - Rendición de Gastos (`l10n_pe_hr_expense_settlement`)

Rendición de entregas a rendir (cuenta 14) desde la app Gastos, según la nota
técnica *Corrección del asiento de liquidación y diseño de campos + conciliación
desde la factura*.

## Flujo

| # | Paso | Asiento |
|---|------|---------|
| 1 | Anticipo al empleado (pago / aprobación, ya existente) | 14 Debe / Banco Haber — socio: empleado |
| 2 | El empleado rinde sus comprobantes en Gastos ("Pagado por: Empleado") y el informe se aprueba | Una **factura de proveedor por comprobante**: 6x + IGV / 42 — socio: proveedor real |
| 3 | Al publicar la factura se liquida sola (o con el botón **Conciliar con Anticipo**) | 42 Debe (proveedor) / 14 Haber (empleado), diario de liquidación, sin caja |
| 4 | Conciliación automática 42 ↔ factura y 14 ↔ anticipo(s) | Factura "Pagada" o "Parcial"; informe "Hecho" |
| 5 | Si se rindió más de lo adelantado, el exceso queda como saldo acreedor del empleado en la 14 y se le reembolsa con un pago normal | 14 Debe / Banco Haber |

## Gasto (`hr.expense`)

- **Proveedor** (campo nativo `vendor_id`, ahora visible también para "Pagado por: Empleado").
- **Tipo de documento**, **Serie** y **Número**: la referencia de la factura queda
  `SERIE-NÚMERO` (número numérico completado a 8 dígitos), que es lo que leen el
  PLE 8.1 y el SIRE.
- **Va al Registro de Compras** (marcado por defecto): marcado, **Proveedor, Tipo de
  documento, Serie y Número son obligatorios** en el formulario y se validan al
  **enviar** el informe (no recién al contabilizarlo). Desmarcado no se exige ninguno:
  la factura va al diario de compras configurado para comprobantes fuera del registro
  (con "No incluir en PLE", fuera del PLE 8.1 y del SIRE) y sin tipo de documento; en
  ese diario `invoice_validation_by_document` no exige un tipo aceptado para el socio.
- Las líneas del informe se abren en su formulario (no se editan en la lista) para que
  siempre se pidan los datos del comprobante.
- Como en una factura de proveedor normal, el gasto no pide asignación de IGV,
  clasificación del bien o servicio, rubro ECPN ni comerciante (el comerciante es el
  proveedor): la asignación de IGV y la clasificación (tabla 30) se configuran en la
  **categoría** (puente `_ple`).
- **Aviso de devolución**: si la descripción o las notas de una línea hablan de dinero
  devuelto ("devolución", "devuelvo", "reintegro", "sobrante") y la categoría no es la de
  devolución, el gasto y el informe muestran un aviso. "Cliente a refacturar" es nativo (`sale_expense`): no aparece si la
  categoría tiene *Volver a facturar gastos = No*.
- **Comprobante único**: al aprobar se bloquea un comprobante ya rendido en otro informe o
  ya registrado como factura de proveedor.
- **Comprobante con varias líneas** (p.ej. ítem gravado + inafecto): botón nativo
  **Dividir gasto**. Las líneas comparten proveedor, tipo y serie-número y salen en
  **una sola factura** con varias líneas.
- La factura va en la **moneda del comprobante** y con el tipo de cambio aprobado
  en el gasto; la fecha de la factura es la fecha del gasto y la fecha contable la
  del informe.
- **Gastos sin comprobante** (sin proveedor, p.ej. movilidad sin sustento): se
  desmarca *Va al Registro de Compras* y van en una factura a nombre del empleado en el
  diario fuera del Registro de Compras; se liquidan contra la 14 como los demás.

## Empleado

Pestaña *Ajustes* → **Centro de costos**: distribución analítica
que se propone en todos sus gastos.

## Liquidación contra el anticipo

**Automática**: al publicar una factura que viene de un informe de gastos se liquida
sola, en su fecha contable (ajuste *Liquidar automáticamente*, activo por defecto). Si
algo lo impide (p.ej. no hay cuenta donde dejar el saldo del empleado) la factura igual
queda publicada, se explica el motivo en el chatter y queda el botón manual.

**Manual**: botón **Conciliar con Anticipo** en la factura. El asistente lista los
anticipos abiertos del empleado (misma búsqueda que la pestaña informativa *Empleado -
Cuenta 14* de `je_approval_expense_flow`); se pueden desmarcar anticipos.

En ambos casos:

- Se liquida **siempre el saldo completo** de la factura: el comprobante ya lo pagó el
  empleado, así que nunca queda deuda con el proveedor.
- Se aplican los anticipos **de la moneda del comprobante** (un gasto en USD consume
  la 1413001, uno en soles la 1413000), del más antiguo al más reciente. Si en el
  informe se eligió un **Anticipo / fondo**, solo se aplica ese. Lo que no alcanza
  queda como **saldo a reembolsar** al empleado en la cuenta 14 de esa moneda.
- Cada línea del asiento se concilia con su propia contrapartida (factura, anticipo),
  así el mayor de la 14 no muestra partidas cruzadas.
- Multimoneda: entre la moneda de la factura y la de la compañía se usa el **tipo de
  cambio de la factura**, así la 42 se cancela por su saldo exacto (mismo importe en
  soles en factura y liquidación). La diferencia contra el tipo de cambio de un
  anticipo en moneda extranjera la genera la conciliación nativa.
- Trazabilidad: botón *Liquidaciones* en la factura, campo *Factura rendida* en el
  asiento y mensaje en el chatter de la factura y del informe. Para deshacer, basta con
  pasar el asiento de liquidación a borrador.

## Cierre de la rendición desde el informe

- **Devolución del sobrante**: categoría de gasto marcada *Devolución de entrega a
  rendir* (sin impuestos; en el gasto se ocultan proveedor, comprobante e IGV). El
  empleado la agrega al informe con el banco o la caja donde devolvió. Al contabilizar
  no genera factura: crea un **cobro** (Debe banco/caja / Haber 14 empleado) conciliado
  con el anticipo. No puede superar el saldo pendiente del anticipo. Un informe que solo
  devuelve queda *Hecho* al registrar el cobro; restablecerlo cancela el cobro.
- **Saldo por liquidar / Liquidar saldo**: el informe contabilizado muestra el saldo
  abierto en la 14 de los anticipos que rindió (positivo: el empleado devuelve;
  negativo: se le reembolsa). El botón abre el pago o cobro nativo ya lleno y concilia
  la 14 al confirmarlo. En moneda extranjera usa el tipo de cambio configurado (puente
  `_exchange_rate`).
- **Anticipo / fondo**: la lista ofrece solo los anticipos de la moneda de los
  comprobantes del informe (sin comprobantes aún, todos); si se elige uno de otra moneda
  se muestra un aviso.
- Solo se contabilizan informes **aprobados** (también por importación, acción masiva
  o RPC).

## Solicitudes de anticipo (Aprobaciones)

En el tipo de aprobación *Crear Pago a Proveedor*, el campo **Anticipo al personal**
(*Entrega a rendir* o *Fondo de caja chica*) hace que el pago vaya a la cuenta 14 de la
moneda de la solicitud (no a la 42), con el empleado como socio. La solicitud tiene
**Moneda**: el pago sale del diario por defecto o de los *Diarios de pago por moneda*
(p.ej. Bcp Dólares), siempre con un **método de pago de salida** (cuenta de pagos
pendientes): si el método por defecto del tipo de aprobación es de entrada o de otro
diario se usa el primer método de salida del diario. Si el diario no tiene cuenta de pagos pendientes, el pago se
registra directo contra el banco/caja para que el anticipo quede en la 14 al publicarse.

**Caja chica**: el fondo usa su propia cuenta y su diario de liquidación (Ajustes). En
el informe se elige el fondo como *Anticipo / fondo*; una vez contabilizado, **Reponer
fondo** crea la solicitud por el total rendido.

## Dividir gasto

Las líneas de un comprobante dividido conservan proveedor y serie-número y salen en una
sola factura; deben **sumar el total del comprobante** (se valida al enviar y al aprobar). Al
cambiar la categoría de una línea, su IGV pasa a ser el de la nueva categoría (o el de
su asignación de IGV).

## Configuración (Gastos → Configuración → Ajustes → Rendición de gastos)

Por compañía:

- **Diario de liquidación**: diario misceláneo (p.ej. "Liquidación de
  Rendiciones"). No debe requerir aprobación (`account_move_approval`). Sin este diario
  no hay liquidación automática.
- **Liquidar automáticamente**: activo por defecto.
- **Comprobantes fuera del Registro de Compras**: diario de compras excluido del PLE.
- **Cuentas de entregas a rendir**: p.ej. 1413000 / 1413001. Vacío: todas las
  cuentas conciliables que empiezan con 14. Para cada moneda se usa la cuenta con esa
  moneda o, si no hay, la que no exige moneda.
- **Fondo de caja chica**: cuenta del fondo y diario de liquidación propios (vacíos:
  los de las rendiciones).

## Módulos puente (auto_install)

- `l10n_pe_hr_expense_settlement_ple` (con `ple_purchase_book`): tipos de documento limitados a
  los diarios de compras de la compañía (`document_in_supplier_invoice`). En la
  **categoría de gasto**:
  - **Asignación de IGV**: *Gravada → operaciones gravadas*, *gravadas y no gravadas*,
    *no gravadas* o *No gravada (exonerada/inafecta)*. Elige el impuesto de compra de la
    compañía cuya base lleva la etiqueta del Registro de Compras (`P_BASE_GDG`,
    `P_BASE_GDM`, `P_BASE_GDNG`, `P_BASE_NG`): primero uno de los impuestos de la
    categoría con esa etiqueta (p.ej. un IGV de 10%), si no el primero de la compañía
    por secuencia. Vacía: impuestos de proveedor de la categoría (nativo).
  - **Clasificación de bienes y servicios** (tabla 30): va a la factura de compra
    (`types_goods_services_id`); con varias líneas, la de la línea de mayor importe.
- `l10n_pe_hr_expense_settlement_document` (con `invoice_validation_by_document`):
  solo se ofrecen los comprobantes aceptados para el tipo de identificación del
  proveedor; un tipo no aceptado se rechaza al enviar el informe. El diario fuera del
  Registro de Compras queda exento de esa validación.
- `l10n_pe_hr_expense_settlement_exchange_rate` (con `invoice_purchase_exchange_rate`):
  ajuste **Tipo de cambio de devoluciones y reembolsos** (por defecto *cobros a TC
  compra y pagos a TC venta*; o siempre venta / siempre compra) para la devolución del
  sobrante y "Liquidar saldo" en moneda extranjera.

Los dos primeros extienden `hr.expense._l10n_pe_get_document_types_domain`, la única
fuente de los tipos ofrecidos y de la validación al enviar y aprobar.

## Notas

- No instalar junto con `hr_expense_cust` ni `hr_expense_extension`: redefinen cómo el
  informe arma las facturas (campos duplicados y facturas dobles). Lo que aportaba
  `hr_expense_extension` que sí aplica a la localización (comprobante único) está
  incluido aquí; la asignación de IGV, el rubro ECPN y el comerciante se retiraron a
  pedido del cliente (no son de la localización peruana).
- Pendientes del Excel de campos del cliente: Tipo de Compra y Factura de importación.
