# -*- coding: utf-8 -*-
{
    'name': 'Account Payment Term Label',
    'version': '18.0.1.0.2',
    'category': 'Accounting/Accounting',
    'summary': 'Etiqueta configurable por línea de término de pago en apuntes contables',
    'description': """
Account Payment Term Label
==========================

Permite configurar una etiqueta por defecto en cada línea de un término de
pago. Esa etiqueta se propaga como `name` de la línea payable/receivable
generada en la factura, reemplazando el patrón nativo "installment #N"
("plazo #N" en es_PE).

Comportamiento
--------------
* Se agrega el campo "Nombre" a las líneas de cada término de pago.
* Al crear una factura con ese término, cada línea payable/receivable toma
  como etiqueta el "Nombre" configurado en la línea del término.
* Si la línea del término no tiene "Nombre", se conserva el comportamiento
  nativo de Odoo ("plazo #N").
* Si el usuario edita manualmente la etiqueta en la factura, ese valor se
  conserva y ya no se sobrescribe al confirmar la factura, restablecerla
  a borrador, cambiar la referencia de pago, o cualquier recompute posterior.
* Al duplicar la factura, el flag manual se resetea (copy=False), por lo
  que las etiquetas nuevas vuelven a salir del término de pago.

Caso de uso típico (Perú)
-------------------------
En el término "Detracción 10%, saldo al crédito 15 días":
    * Línea 1 → Nombre = "Detracción"
    * Línea 2 → Nombre = "Saldo"

Todas las facturas con ese término mostrarán automáticamente esas
etiquetas en las líneas de cuentas por pagar, sin el patrón "plazo #N".
""",
    'author': 'Empiria',
    'website': 'https://www.empiria.pe',
    'license': 'LGPL-3',
    'depends': ['account', 'payment_term_lines'],
    'data': [
        'views/account_payment_term_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
