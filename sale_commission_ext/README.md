# Comisiones de venta - moneda del plan y facturas publicadas (`sale_commission_ext`)

Extiende los **Planes de comisión** estándar (`sale_commission`, Ventas → Comisiones).

## Qué cambia

| Tema | Estándar | Con este módulo |
|------|----------|-----------------|
| Facturas consideradas | Todas excepto canceladas (**incluye borradores**) | Solo **publicadas** (facturas y notas de crédito) |
| Moneda del plan | Siempre la de la compañía (no editable) | Campo **Moneda** en el plan (PEN o USD); editable solo en borrador |
| Objetivos / niveles de comisión | En moneda de la compañía | En la moneda del plan |
| Logro de un documento en la moneda del plan | Convertido a moneda de la compañía | **Importe exacto** del documento |
| Logro de un documento en otra moneda | Subtotal / `invoice_currency_rate` (falla con tasa 0; ignora TC forzado) | Importe **contabilizado** en moneda de la compañía (respeta el TC forzado) convertido al TC de su fecha |
| Ajustes manuales en otra moneda | Conversión invertida (multiplicaba por la tasa) | Conversión correcta |

Un plan en la moneda de la compañía calcula igual que el estándar, salvo los borradores y
que usa el importe contabilizado (el estándar se cae con "division by zero" ante facturas de
importe cero con `invoice_currency_rate` en 0, frecuentes en jeal).

## Tipo de cambio

Se usa la tasa de `res.currency.rate` con el mismo criterio que Odoo (compañía raíz,
última tasa hasta la fecha del documento). El puente `sale_commission_ext_exchange_rate`
(auto_install con `invoice_purchase_exchange_rate`) usa la tasa de **venta** cuando hay
compra y venta para la misma fecha.

## Uso

1. Ventas → Comisiones → Planes de comisión → Nuevo.
2. Elegir la **Moneda** (p.ej. USD) antes de aprobar.
3. Objetivos, comisión al llegar al objetivo, logros y comisiones se ven y calculan en esa moneda.
