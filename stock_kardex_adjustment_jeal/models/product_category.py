# -*- coding: utf-8 -*-
from odoo import fields, models

# Tabla 5 SUNAT - Tipo de existencia
STOCK_TYPES = [
    ('01', '01 - Mercaderías'),
    ('02', '02 - Productos terminados'),
    ('03', '03 - Materias primas'),
    ('04', '04 - Envases'),
    ('05', '05 - Materiales auxiliares'),
    ('06', '06 - Suministros'),
    ('07', '07 - Repuestos'),
    ('08', '08 - Embalajes'),
    ('09', '09 - Subproductos'),
    ('10', '10 - Desechos y desperdicios'),
    ('91', '91 - Otros 1'),
    ('92', '92 - Otros 2'),
    ('93', '93 - Otros 3'),
    ('94', '94 - Otros 4'),
    ('95', '95 - Otros 5'),
    ('96', '96 - Otros 6'),
    ('97', '97 - Otros 7'),
    ('98', '98 - Otros 8'),
    ('99', '99 - Otros'),
]


class ProductCategory(models.Model):
    _inherit = 'product.category'

    kardex_stock_type = fields.Selection(
        selection=STOCK_TYPES, string='Tipo de existencia (tabla 5)',
        help='Tipo de existencia de los libros 12.1 y 13.1 para los productos de '
             'la categoría que no tienen uno propio.')
