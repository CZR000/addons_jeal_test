# Conciliación intercompany por documento (`empiria_intercompany_reconciliation`)

Reporte de **control** para el Grupo Empiria (Odoo 18): para cada par de empresas del
grupo y bloque de cuentas, si sus saldos de balance cuadran a una fecha de corte y, si
no, **qué documento o movimiento** lo explica y qué hacer. **No crea, modifica ni
concilia asientos.**

## Menús

- *Contabilidad › Informes › Conciliación intercompany*: Generar conciliación,
  Ejecuciones, Resumen por par, Detalle de diferencias.
- *Contabilidad › Configuración › Conciliación intercompany* (Responsable).

## Universo y bloques

Apuntes **publicados** hasta la fecha de corte, en cuentas de balance con socio, cuyo
socio es otra empresa del grupo (se reconoce por **RUC**: direcciones y almacenes con
el mismo RUC cuentan como la misma empresa).

Cada par A↔B tiene **dos bloques, según quién cobra**:

| Bloque | Cuentas de la empresa que cobra | Cuentas de la que paga |
|---|---|---|
| A por cobrar / B por pagar | 12, 13, 14, 16, 17, 19 de A con B (incluye anticipos 122) | 41 a 47 de B con A (incluye 4220 y 46) |
| B por cobrar / A por pagar | lo mismo en sentido inverso | |

La contrapartida de cada línea queda en el mismo bloque: una 12 contra una 46 o una 16
contra una 42 se emparejan sin tratamiento especial. Si las familias de cuenta difieren
(familia préstamos 16, 17, 46, fija en el código), la línea queda **Conciliado – cuenta
distinta** con la observación "Documento en ambas empresas, en cuentas distintas (A en
1212001 / B en 4699001)" (campo *Cuenta distinta*, filtrable y agrupable); no es
diferencia ni pendiente. El resumen muestra
además el **Total del par** (suma de los dos bloques).

Diferencia del bloque = saldo de A con B + saldo de B con A. **Control** = diferencia −
suma de las categorías: debe ser 0 (cada apunte cae en exactamente un grupo).

## Periodo y filtros de fecha

- **Generar**: *Año en curso* (por defecto), *Mes en curso*, *Últimos 12 meses*, *Otro
  año*, *Desde - hasta* o *Sin fecha desde*. Se compara la fecha contable. El
  emparejamiento usa siempre todo el historial hasta el corte; la fecha desde solo
  decide qué se lista y cuenta como pendiente: una línea se muestra si su fecha o la de
  su contraparte es igual o posterior (un documento del 26/12 en una empresa y del 01/01
  en la otra no sale como "sin registrar"). **Todo apunte anterior a la fecha desde**
  se resume en una línea por par y bloque, *Arrastre anterior al periodo*, que es igual
  a la *Diferencia al inicio* (saldos al día anterior): diferencia al inicio + lo del
  periodo = diferencia final. Un documento que cruza la fecha desde se muestra en el
  periodo solo con el efecto de sus apuntes del periodo (la observación dice cuánto quedó
  en el arrastre). El total del par es el mismo con o sin fecha desde y el control sigue
  en 0.
- **Ejecución diaria**: la configuración define su fecha desde (sin límite, año en curso
  —por defecto—, últimos N meses o fecha fija). Nuevos y resueltos se comparan solo
  entre corridas con la misma fecha desde.
- **Resumen por par y Detalle**: filtros dinámicos *Año en curso* y *Mes en curso* por
  la fecha de la línea.
- **Ejecuciones, Resumen por par y Detalle**: filtros *Última ejecución* (por defecto en
  los menús), *Fecha de corte* (año / trimestre / mes) y búsqueda *Corte desde / hasta*;
  en el detalle también *Fecha del documento* (año / trimestre / mes) y *Fecha desde /
  hasta*, y agrupar por mes.

## Reglas (en orden; cada apunte se empareja una sola vez)

| # | Regla | Tolerancia | Resultado |
|---|---|---|---|
| 14 | Emparejamiento manual (se aplica primero: prevalece la decisión del usuario) | diferencia con motivo | Conciliado manual |
| 2 | Diario de diferencia de cambio | — | Diferencia de cambio (agregada) |
| 3-4 | Comprobante por número (venta: número del comprobante; compra: Referencia; sin espacios ni ceros) y comparación de moneda, total, importe en cuentas IC, mes y tipo de cambio | total 0.01; redondeo: efecto ≤ S/ 1.00 | Conciliado, Redondeo, Moneda distinta, Anticipo aplicado distinto, Importe distinto (solo si difiere el importe en la moneda del documento), Periodo distinto, Tipo de cambio distinto (mismo importe en la moneda del documento, distinto en soles) |
| 5 | Mismo número, importe y moneda con otra serie (C01 vs FC01); si la contraparte está en 0 en las cuentas IC, *Sin registrar en el receptor* | 0.05 | NC con serie distinta |
| 6 | Mismo importe y moneda, otro número, fecha cercana | 0.05 · 5 días | Documento con número distinto |
| 7 | El número en la otra empresa en cualquier estado o socio | exacto | Nota: en borrador / anulada / con otro socio |
| 8 | Sin par | — | Sin registrar en el receptor / Compra sin factura del emisor |
| 9 | Asiento que se anula en la misma empresa; provisión y su reversión o extorno | 0.05 | Sin efecto (o diferencia de cambio si queda residuo en soles) |
| 10 | Pago ↔ cobro, misma moneda: asiento contra asiento y luego línea contra línea | 0.05 · 15 días | Conciliado |
| 11 | Pago en otra moneda, en soles | 1 % o S/ 1 · 15 días | Moneda distinta (conciliado, con el residuo por tipo de cambio en la observación) |
| 12 | Pagos agrupados (suma de un asiento o de un día contra una o varias líneas); otra moneda exacta en soles | 0.05 · 20 días | Conciliado |
| 13 | Compensación de 3 empresas: pago de banco/caja cuya glosa menciona a otra empresa del grupo | 0.05 · 20 días | Compensación de 3 empresas / Compensación incompleta: falta registrar en X |
| 13 | Las dos empresas registraron del mismo lado (ambas 122, ambas 42, 16 contra 12): mismo importe, sentido contrario | 0.05 · 20 días | Conciliado – cuenta distinta (cada bloque con su parte) |
| 15 | Sin par, por diario o glosa | — | Pago/cobro, Detracción, Retención, Saldo de apertura, Asiento manual sin contrapartida (también los ajustes por redondeo, con su observación); diferencia de cambio por su glosa |
| 16 | Pago más retención: un pago es igual al pago de la otra empresa más su retención del 3 % | S/ 1 · 20 días | Conciliado ("Pago más retención 3%") |
| 17 | Un pago o documento contra la suma de 2 o 3 partidas pendientes de la otra empresa, de cualquier categoría | S/ 1 · 20 días | Conciliado ("Pago agrupado: N líneas") |
| 18 | Anticipo o préstamo en varias partes: suma de las partidas pendientes de cada empresa con el mismo comprobante citado en la glosa o, si no cita ninguno, del mismo tipo (anticipo / préstamo) | S/ 1 | Conciliado; si no cuadran, quedan pendientes con la marca *Anticipo aplicado parcialmente* |

Tipo de cambio distinto: si la diferencia no supera el 0.02 % del importe en soles (o
S/ 1), queda como Redondeo (configurable).

Las reglas 16 a 18 solo combinan partidas pendientes de un mismo par de empresas, y cada
partida se usa una sola vez. Después, **sugerencias** (no emparejan): en el detalle de
una línea pendiente, *Posible contraparte* cuando la glosa cita un comprobante pendiente
de la otra empresa, o cuando una partida de la otra empresa difiere hasta 2 % en monto y
30 días en fecha; el botón *Emparejar con la sugerencia* abre el asistente con las dos
líneas.

**No son pendientes**: Conciliado, Conciliado – cuenta distinta, Redondeo (con
contrapartida y efecto ≤ S/ 1, con el importe en la observación), Moneda distinta con
efecto ≤ 0.05 o en pagos, Diferencia de cambio, Compensación de 3 empresas, Sin efecto,
Conciliado manual y Arrastre anterior al periodo.

Los residuos de los emparejamientos (tolerancia o tipos de cambio distintos) quedan en
su propia categoría para que el control siga en 0.

## Acciones (grupo Conciliación IC / Responsable)

- **Marcar revisado** (comentario obligatorio): la línea deja de contar como pendiente;
  su importe sigue en la diferencia. Se reconoce en las siguientes ejecuciones por su
  huella (empresa + asiento + importe): si el importe cambia, vuelve a pendiente.
- **Emparejar a mano**: líneas del mismo par de empresas (o de una compensación entre
  tres empresas, con una línea de cada una); si hay diferencia, la explicación es
  obligatoria. Las líneas pasan a *Conciliado manual* en esta y en las siguientes
  ejecuciones. **Deshacer** las devuelve a pendiente al instante, con la categoría que
  tenían.

## Ejecución diaria

Acción programada diaria con corte del día: si la configuración no tiene empresas usa
todas las que tienen RUC, y si no tiene responsable lo deja escrito en la ejecución.
Conserva revisiones y
emparejamientos, marca los **pendientes nuevos** frente a la ejecución anterior y crea
una actividad al **Responsable** si hay pendientes nuevos o el control de algún par no
es 0. Se conservan las últimas N ejecuciones automáticas (configurable) y todas las de
cierre de mes.

## Excel

*Exportar a Excel* genera `Conciliacion_Intercompany_documentos_DD-MM-AAAA.xlsx` con las
hojas Notas, Resumen (categorías con SUMIFS sobre el Detalle y control), Por categoría,
Detalle, Emparejamientos manuales y Reglas (Arial, dos decimales, encabezados fijos y
filtros). Si el control no es 0 el archivo sale como `_NO_DEFINITIVA`.

## Seguridad

- Conciliación IC / Usuario (implícito para los usuarios de contabilidad): generar, ver,
  abrir documentos y exportar.
- Conciliación IC / Responsable: además revisar, emparejar, deshacer y configurar.
- El detalle solo se ve para las empresas a las que el usuario tiene acceso; los pares
  (totales) se ven completos.

## Arquitectura

`engine.py` es Python puro (sin Odoo): recibe los apuntes como diccionarios y devuelve
pares y detalle. Lo usa el modelo `ic.reconciliation.run` (que lee los apuntes con el
ORM por empresa y en bloques de 2,000) y sirve para validar contra producción con
scripts de solo lectura.
