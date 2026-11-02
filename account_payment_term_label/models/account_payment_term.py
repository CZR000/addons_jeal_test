# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountPaymentTermLine(models.Model):
    _inherit = 'account.payment.term.line'

    name = fields.Char(
        string='Nombre',
        translate=True,
        help="Etiqueta por defecto que se copiará al `name` de la línea "
             "payable/receivable generada en la factura para este plazo. "
             "Si se deja vacío, se usará el patrón nativo 'plazo #N'.",
    )
