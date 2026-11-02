# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Convenio para evitar la doble tributacion (definido en rent_4ta con 0-4 y
    # solo para RR.HH.). Se completa con las mismas opciones que el CDI de la
    # factura (tabla 25 SUNAT: 00-09) y se hace visible para Contabilidad.
    # Se mantienen codigos de un digito para no cambiar valores existentes ni
    # el reporte de renta de 4ta.
    double_taxation = fields.Selection(
        selection_add=[
            ('5', '[5] Estados Unidos Mexicanos'),
            ('6', '[6] República de Corea'),
            ('7', '[7] Confederación Suiza'),
            ('8', '[8] Portugal'),
            ('9', '[9] Otros'),
        ],
        ondelete={
            '5': 'set null',
            '6': 'set null',
            '7': 'set null',
            '8': 'set null',
            '9': 'set null',
        },
        groups='hr.group_hr_user,account.group_account_invoice',
    )
    # Tipo de renta por defecto para facturas No Domiciliado (tabla 31).
    nodom_type_rent_id = fields.Many2one(
        comodel_name='type.rent',
        string='Tipo de Renta (No Domiciliado)',
        help='Se copia a las facturas No Domiciliado de este proveedor al '
             'crearlas. Puede cambiarse en cada factura.',
    )
