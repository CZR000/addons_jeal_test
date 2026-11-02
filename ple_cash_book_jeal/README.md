# PLE Libro Caja y Bancos 1.1 / 1.2 (`ple_cash_book_jeal`)

Rehace la generación del **Libro Caja y Bancos** de `ple_cash_book`
(`ple.report.cash.bank`, Informes PLE → Libro Caja y Bancos) según el pedido
"PLE 1.1 y 1.2 Libro Caja y Bancos" (02/10/2026). Se instala a mano; no cambia el
formulario del reporte.

## Configuración previa (C1, la hace el consultor)

Contabilidad → Configuración → Plan contable, columna **PLE** (`ple_selection`):

- **1.1 Efectivo**: 101 Caja, 102 Fondos fijos, 103 Efectivo en tránsito / Rendición.
- **1.2 Cuentas corrientes**: solo cuentas de bancos (cuenta por defecto de un diario
  tipo Banco con *Cuenta bancaria*).
- Cuentas transitorias, de pagos/cobros pendientes o de transferencia de liquidez:
  1.1 o vacío.

## Qué hace

| Pedido | Comportamiento |
|---|---|
| D1 | El 1.2 toma el banco (código SUNAT) y la cuenta del **diario de banco** de la cuenta (o de la cuenta bancaria de la cuenta contable). Si una cuenta 1.2 con movimientos no tiene banco o el banco no tiene código SUNAT, **no se genera** y se indica la cuenta. |
| D2 | El 1.1 incluye las líneas de cuentas 1.1 con los 19 campos: documento relacionado del propio asiento (el comprobante, o el único comprobante conciliado directamente o a través del pago; no se usa el tipo/serie de la línea porque `invoice_type_document` los copia a todas las líneas del extracto al conciliar; sin comprobante: `00`, serie vacía y número = asiento), fecha de operación del comprobante, glosa de la línea, glosa referencial del asiento y dato estructurado `140100`/`080100`/`080200` & periodo & CUO & correlativo del comprobante. |
| D3 | Medio de pago (tabla 1): por defecto el del **método de pago** o el del **diario** (Diario → Medio de pago (PLE); en cada método de pago, p.ej. cheques 007). Se copia al asiento del pago o de la línea de extracto y es editable (asiento → Otra información; lista y formulario de transacciones bancarias). En el reporte, si el asiento no lo tiene: el del pago, el que se deduce de la operación bancaria (cheque 007, depósito 001; también al crear la línea de extracto) o el del diario. Si aún falta, se informa **003** (el campo es obligatorio) y el botón «Sin medio de pago» lista esos asientos para revisarlos. |
| D4 | Girador/beneficiario: socio del asiento o del extracto; si no hay, el de la única contrapartida; sin socio o con varios, `-|-|VARIOS`. Socio sin tipo o número de documento: aviso. |
| D5 | CUO y correlativo **por línea**, con la misma regla que el Libro Diario 5.1 (`get_journal_correlative`). Un CUO + correlativo repetido se informa en el aviso. |

Campo 12 (n° de transacción): referencia del asiento/extracto, del pago o el nombre
del asiento (solo letras y números, máx. 20). Campo 8: etiqueta del extracto o de la
línea.

## Avisos del reporte

El reporte se genera y resume lo que hay que completar, con botones para corregirlo:

- **Sin medio de pago**: lista editable (también en bloque) de los movimientos bancarios
  sin medio de pago; se asigna y se vuelve a generar.
- **Socios sin documento**: contactos sin tipo o número de documento.

## Validación

Por cuenta 1.2, debe/haber del TXT = mayor del periodo (se incluyen todas las líneas
publicadas de la cuenta). El nombre del TXT lleva el indicador de contenido
(`…01111` con datos, `…01011` vacío).
