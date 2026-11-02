# Perú - Compensación de Cuentas

Módulo Odoo 18 que automatiza la compensación de facturas de cliente y proveedor
cuando el mismo socio actúa como ambos (CxC contra CxP).

## Instalación

1. Copiar la carpeta `l10n_pe_account_compensation` en el directorio de addons.
2. Reiniciar el servicio Odoo.
3. Activar modo desarrollador → Aplicaciones → Actualizar lista de aplicaciones.
4. Buscar "Compensación" e instalar.

## Configuración

Ir a **Contabilidad → Configuración → Ajustes**, ubicar la sección
"Compensación de Cuentas" y configurar:

| Campo | Valor sugerido (Connected Resources) |
|---|---|
| Diario de compensación | Provisiones varias |
| Cuenta puente cliente (Debe) | 4212001 - Facturas, boletas y otros comprobantes por pagar - Emitidas M.E. |
| Cuenta puente proveedor (Haber) | 1212001 - Facturas, boletas y otros comprobantes por cobrar - Emitidas en cartera M.E. |
| Cuenta ganancia dif. cambio | 7760000 - Diferencia en cambio |
| Cuenta pérdida dif. cambio | 6760000 - Diferencia de cambio |

## Uso

1. Abrir una factura de cliente o proveedor **publicada** con saldo pendiente.
2. Clic en **Aplicar Compensación** (visible solo para el grupo Asesor Contable).
3. El wizard precarga las facturas del socio del tipo contrario.
4. Ajustar montos, fecha, tipo de cambio.
5. Clic en **Generar asiento** → asiento creado en **borrador** en el diario configurado.
6. Revisar el asiento y clic en **Confirmar** → conciliación automática de ambas facturas.

## Reverso

En un asiento de compensación publicado aparece el botón **Revertir Compensación**
que rompe la conciliación en las facturas afectadas y genera un asiento de reverso.

## Autor

Sinetics - https://www.sinetics.com.pe
