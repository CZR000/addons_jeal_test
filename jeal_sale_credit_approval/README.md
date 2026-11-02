# jeal_sale_credit_approval

Límite de crédito y aprobación de ventas al crédito (Odoo 18 Enterprise).

**Autor:** Empiria
**Versión:** 18.0.1.4.1
**Depende de:** `sale`, `account`, `stock`, `mail`

## Qué hace

Impide confirmar una cotización **al crédito** cuando el cliente excede su
línea de crédito o tiene deuda vencida, salvo aprobación del aprobador desde
su correo (botones Aprobar / Rechazar, enlace de un solo uso de 72 h).

## Instalación

1. Copiar la carpeta `jeal_sale_credit_approval/` en el directorio de addons.
2. Actualizar la lista de aplicaciones e instalar el módulo.
3. Ir a **Ventas › Configuración › Ajustes**, bloque *Aprobación de crédito*:
   - Elegir el **aprobador de crédito** (debe tener correo).
   - Elegir la **vigencia del enlace** (24 h, 48 h, 3 días o 1 semana).
   - En **¿Cuándo pedir aprobación?**, decidir si las facturas vencidas exigen
     aprobación y con cuántos días de gracia.
   - En **¿Qué cuenta como deuda del cliente?**, elegir entre facturas
     pendientes, facturas + pedidos sin facturar (recomendado) o todo
     (incluye borradores). Anticipos y notas de crédito siempre se restan.
4. Asignar el grupo **Administrador de créditos** a los usuarios designados.
5. Cargar el **límite de crédito** por cliente (pestaña *Crédito* del contacto).

## Flujo

1. En la cotización se marca **Tipo de venta = Crédito**.
2. Al confirmar, si la deuda total + esta cotización excede el límite, o el
   cliente tiene deuda vencida, o el límite es 0, Odoo **bloquea** y pide
   **Enviar solicitud al aprobador**.
3. El aprobador recibe el correo y decide con **Aprobar / Rechazar** (página
   pública con token, segundo clic de confirmación).
4. Aprobado → el vendedor confirma. Rechazado → motivo obligatorio y aviso.
   Vencido (72 h) → el vendedor **Reenvía** con un enlace nuevo recalculado.
5. Si el importe sube por encima de lo aprobado, se pide nueva aprobación.

Toda la trazabilidad queda en el **chatter** del documento.

## Reportes

- **Ventas › Crédito › Reporte línea de crédito** (límite, deuda, vencida,
  disponible, % de uso por cliente).
- **Ventas › Crédito › Solicitudes de aprobación**.

## Nota de alcance

La **composición exacta de la deuda total** es parametrizable en Ajustes
porque el documento funcional no la fijó. Validar con el cliente qué piezas
entran antes de pasar a producción.

> Prototipo de referencia. Requiere pruebas de QA en un entorno de staging
> antes de usarse en producción.
