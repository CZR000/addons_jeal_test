# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    advance_role = fields.Selection(
        selection=[
            ("origin", "Origen (crea el anticipo)"),
            ("application", "Aplicacion (linea negativa)"),
        ],
        string="Rol en anticipos",
        help="Origen: al publicar la factura crea el documento de anticipo. "
             "Aplicacion: linea negativa que descuenta un anticipo.",
    )
