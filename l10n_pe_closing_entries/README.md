# Asientos de Cierre Contable (Perú)

Genera los asientos de cierre del ejercicio a partir de la configuración del
plan contable, resolviendo **cadenas de cierre de varios niveles** y evitando
la duplicación de asientos entre corridas.

## Configuración

En cada cuenta (*Contabilidad → Configuración → Plan Contable*), pestaña
**Configuración de Cierre**:

| Campo | Significado |
|---|---|
| **Cuenta de Cierre** | Contrapartida. **Si está vacía, la cuenta no se cierra.** |
| **Nivel de Cierre** | Calculado. Saltos hasta el final de la cadena. |
| **Es Cuenta de Cierre/Resultado** | Calculado (editable). Se marca cuando otras cuentas la usan como destino. |
| **Detalle del Asiento** | `Sin detalle` / `Por producto` / `Por contacto`. |

### Cadenas de varios niveles

Una cuenta destino puede tener a su vez su propia cuenta de cierre:

```
60 Compras ──┐
             ├──► 89 Determinación del Resultado ──► 59 Resultados Acumulados
70 Ventas ───┘
   nivel 2              nivel 1                          nivel 0
```

El asistente calcula el nivel (`closing_depth`) de cada cuenta y procesa la
cadena **de mayor a menor nivel**:

1. **Paso 1 (nivel 2):** 60 y 70 se saldan contra 89.
2. **Paso 2 (nivel 1):** 89 —con su saldo propio *más* lo recibido en el paso
   anterior— se salda contra 59.

Cada paso genera **asientos independientes**, nunca se mezclan eslabones
distintos en un mismo asiento. El importe transferido se acumula en memoria, de
modo que el paso 2 ve el saldo correcto aunque el asiento del paso 1 siga en
borrador.

Las cadenas cíclicas (A → B → A) se rechazan al guardar la configuración.

## Idempotencia: volver a correr el cierre

Los asientos generados quedan marcados con `is_closing_entry`, el nivel y el
periodo cerrado. El cálculo de saldos incluye **los apuntes publicados y los
asientos de cierre del propio módulo aunque estén en borrador**.

Consecuencia: si vuelve a ejecutar el asistente para el mismo periodo,

- las cuentas ya cerradas presentan saldo cero y **no se vuelven a incluir**;
- si no queda nada pendiente, el asistente lo informa en lugar de crear
  borradores duplicados;
- si hubo movimientos nuevos, sólo se cierran esos saldos pendientes.

Para regenerar desde cero, marque **«Reemplazar borradores existentes»**: se
eliminan los asientos de cierre en borrador del periodo antes de recalcular.
Los asientos **publicados nunca se eliminan** (deben revertirse manualmente).

## Opciones del asistente

- **Agrupación de asientos**: un asiento por nivel, por nivel y clase de cuenta,
  o por nivel, clase y signo del saldo (por defecto).
- **Analítica**:
  - `Replicar` (recomendado): las cuentas con política analítica obligatoria se
    desglosan por distribución analítica, de modo que las líneas de cierre la
    conservan y **no hace falta saltarse la validación**.
  - `Sin distribución`: comportamiento clásico; pide confirmación explícita
    listando las cuentas afectadas.
- **Publicar asientos**: si se desmarca, quedan en borrador para revisión.

## Notas técnicas

- Los saldos se agregan con `_read_group` (API de Odoo 17/18); son como máximo
  tres consultas, una por modo de detalle.
- El modo analítico `Replicar` recorre los apuntes en Python (los campos JSON no
  son agrupables en SQL). Con volúmenes muy altos, considere restringir el
  periodo o usar el modo `Sin distribución`.
- `account.account.code` es dependiente de compañía en Odoo 18: el asistente
  fija la compañía con `with_company` antes de clasificar por clase PCGE.
- Las líneas en moneda extranjera informan `currency_id` y `amount_currency`;
  el asiento se registra en la moneda de la compañía.

## Actualización desde 18.0.0.x

`migrations/18.0.1.0.0` convierte `detailed_by_product` en `closing_detail` y
recalcula `closing_depth` e `is_closing_account`. Revise la configuración del
plan contable tras la actualización: ahora **cualquier** cuenta con
«Cuenta de Cierre» se cierra, incluidas las que antes estaban marcadas como
cuenta de resultado.

## Tests

```bash
odoo -d <bd> -i l10n_pe_closing_entries --test-enable --test-tags /l10n_pe_closing_entries
```
