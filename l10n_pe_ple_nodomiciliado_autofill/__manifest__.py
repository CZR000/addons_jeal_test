# -*- coding: utf-8 -*-
{
    'name': 'PLE Purchase Book - Autorelleno No Domiciliado',
    'version': '18.0.4.0.0',
    'summary': 'Tipo de documento (91) en facturas No Domiciliado y control '
               'del sustento de crédito fiscal según SUNAT.',
    'description': """
Ajustes para facturas de proveedor marcadas como "No Domiciliado":

* Tipo de Documento de la cabecera (l10n_latam_document_type_id): se asigna
  (91) Comprobante de No Domiciliado (campo 4 del RCE No Domiciliados). Para
  el resto de facturas se respeta el cálculo estándar de Odoo.
* Sustento del crédito fiscal (pestaña No Domiciliado: inv_type_document,
  inv_serie, inv_correlative): ya NO se autorrellena desde la referencia.
  Lo completa el usuario. El tipo de documento solo admite los códigos
  aceptados por SUNAT para el campo 10: 00, 46, 50, 51, 52 y 53.

Cambios 18.0.2.0.0
------------------
* Se elimina el autorrelleno de Serie, Correlativo y Tipo de documento del
  sustento (provocaba los errores 418 y 403 de SUNAT).
* El cálculo del tipo de documento de cabecera llama al cálculo estándar
  antes de asignar el 91, para no afectar facturas nacionales.
* No se modifican datos existentes: las facturas que ya tienen el 91 en el
  sustento deben corregirse manualmente.

Cambios 18.0.2.0.1
------------------
* Los datos del sustento (tipo, serie, año DUA/DSI y correlativo) no se
  copian al duplicar una factura.

Cambios 18.0.2.1.0
------------------
* CDI: se autocompleta desde el convenio del contacto o el código de
  convenio del país (00 si el país no tiene convenio). No pisa un valor
  elegido por el usuario ni recalcula facturas existentes.
* Al publicar una factura o nota de crédito de proveedor No Domiciliado se
  exige: Tipo de Renta, CDI, país del proveedor (con código SUNAT) e
  identificación del proveedor.

Cambios 18.0.2.2.0
------------------
* En facturas y notas de crédito de proveedor No Domiciliado, Tipo de Renta y
  CDI son obligatorios al guardar (formulario, pestaña No Domiciliado).

Cambios 18.0.3.0.0
------------------
* Sustento: el año de emisión DUA/DSI es obligatorio solo con sustento 50 o 52.
* Al publicar se exige además: tipo de documento de cabecera 00, 91, 97 o 98,
  número del comprobante (referencia) y razón social del proveedor.
* Contacto: el convenio (rent_4ta) se amplía a las 10 opciones del CDI y se
  hace visible para Contabilidad. Nuevo campo Tipo de Renta (No Domiciliado).
  Para contactos principales de país distinto de Perú son obligatorios el
  convenio, el tipo de renta y el número de identificación.
* La factura No Domiciliado hereda del proveedor el convenio y el tipo de
  renta al crearse (no pisa valores ya elegidos).

Cambios 18.0.3.0.1
------------------
* Al elegir un proveedor No Domiciliado, el tipo de documento de cabecera
  queda en 91 aunque invoice_validation_by_document asigne Boleta/Factura
  segun el tipo de identificacion del socio.
    """,
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'category': 'Accounting/Localizations',
    'license': 'LGPL-3',
    'depends': [
        'ple_purchase_book',
        'l10n_pe',
        'rent_4ta',
        'invoice_validation_by_document',
    ],
    'data': [
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
