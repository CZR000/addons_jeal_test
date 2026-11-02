# Anticipos y Revolventes (`l10n_pe_advance_conciliation`)

Módulo Odoo 18 para el control de anticipos de clientes/proveedores y
revolventes mediante documentos con saldo propio (ANTC / REV), con creación,
aplicación y conciliación automáticas.

**Autor:** Empiria · **Versión:** 18.0.1.1.0 · **Cliente:** JEAL

## Qué hace

- Al publicar una factura con un producto de rol *Origen*, crea el documento
  de anticipo (ANTC) con su saldo.
- Un depósito al haber de la cuenta de control del revolvente crea el documento
  REV.
- Wizard **Aplicar anticipos** (facturas en borrador): inserta la línea negativa
  y concilia la cuenta de control al publicar.
- Wizard **Aplicar revolvente** (facturas publicadas): reparte por FIFO y genera
  el asiento de compensación automático.
- Wizard **Cerrar saldo residual** por tolerancia de redondeo.
- Reportes: saldos por documento (lista/pivote/gráfico), estado de cuenta (PDF)
  y cuadre del módulo contra el mayor.

## Menú

Ya no es una aplicación propia. Vive dentro de Contabilidad:

- **Contabilidad → Anticipos y Revolventes**: anticipos de clientes, anticipos
  a proveedores, revolventes e Informes (saldos por documento, detalle de
  aplicaciones, estado de cuenta por socio, cuadre contra contabilidad).
- **Contabilidad → Configuración → Anticipos y Revolventes**: configuración y
  migración de saldos iniciales (grupo Anticipos / Responsable).

Requiere Contabilidad Enterprise (`accountant`).

## Revolventes

- Cada apunte al haber de la cuenta de control (con socio, en la moneda de la
  configuración y en un diario configurado) crea su REV, enlazado a ese apunte
  exacto. También funciona desde la conciliación bancaria.
- "Aplicar revolvente" solo en facturas de cliente publicadas y en la moneda
  del revolvente. Compensa el saldo neto de la factura (después de la
  detracción), reparte por FIFO y concilia todas las cuotas por cobrar.
- El asiento de compensación enlaza la factura y los REV usados. Si se revierte
  o pasa a borrador, las aplicaciones se anulan y el saldo se libera.
- Un depósito cuyo REV ya tiene aplicaciones no puede pasarse a borrador.

## Cierre por redondeo

Por ahora todo cierre va a la cuenta de gasto por redondeo (6593004), al debe o
al haber según el tipo de documento y el signo del saldo.

## Instalación

1. Copiar la carpeta a `addons/`.
2. Actualizar lista de aplicaciones e instalar **Anticipos y Revolventes**.
3. Configurar en *Anticipos y Revolventes → Configuración*.

Ver la guía de configuración y los casos de prueba entregados por separado.

## Pendientes de decisión (ver documento de diseño, sección 10)

1. **Tipo de cambio entre monedas.** Por defecto el módulo usa el TC de la
   factura/fecha del movimiento (`currency._convert`). Está marcado en el código
   como el punto a confirmar con contabilidad.
2. **Disparador del revolvente.** Acotado por `revolving_journal_ids` en la
   configuración: solo los diarios listados crean revolvente. Si se deja vacío,
   cualquier haber a la cuenta lo dispara.
3. **Facturación electrónica (SUNAT).** Las líneas negativas van dentro de la
   factura; validar la emisión con el módulo de e-invoicing en uso.
4. **Migración de saldos iniciales.** Wizard preliminar incluido; dimensionar y
   validar contra el cuadre.

## Nota

Este módulo requiere pruebas en una instancia Odoo 18 real. La lógica de
conciliación, el cálculo de IGV incluido en las líneas de aplicación y el
tratamiento multimoneda del depósito son los puntos a verificar primero.
