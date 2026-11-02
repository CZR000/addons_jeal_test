# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductConversion(models.Model):
    _name = 'jeal.product.conversion'
    _description = 'Tabla de conversión de productos (recepción → OC)'
    _rec_name = 'product_source_id'
    _order = 'product_source_id'

    product_source_id = fields.Many2one(
        'product.product',
        string='Producto recibido',
        required=True,
        ondelete='cascade',
    )
    product_target_id = fields.Many2one(
        'product.product',
        string='Producto de OC',
        required=True,
        ondelete='restrict',
    )
    factor = fields.Float(
        string='Factor de conversión',
        default=1.0,
        digits='Product Unit of Measure',
        help='Cantidad OC = cantidad recibida × factor. '
             'Deje 1.0 para conservar la misma cantidad.',
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ('unique_source_per_company',
         'UNIQUE(product_source_id, company_id)',
         'Ya existe una conversión para este producto en esta compañía.'),
    ]

    @api.model
    def _get_conversion(self, product, company=None):
        """Devuelve el registro activo de conversión para el producto dado
        en la compañía indicada (o la actual si no se pasa).
        Recordset vacío si no hay match."""
        if not product:
            return self.browse()
        company = company or self.env.company
        return self.search([
            ('product_source_id', '=', product.id),
            ('company_id', '=', company.id),
        ], limit=1)