from odoo import fields, models


class HrExpenseIcProduct(models.Model):
    """Producto de la empresa que asume el gasto para cada categoría de gasto de
    otra empresa del grupo, cuando el producto del gasto no existe en ella."""
    _name = 'hr.expense.ic.product'
    _description = 'Equivalencia de categoría de gasto intercompany'
    _check_company_auto = True
    _rec_name = 'origin_product_id'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Empresa que asume el gasto',
        required=True, default=lambda self: self.env.company, index=True,
    )
    # La categoría es de otra empresa: sin check_company.
    origin_product_id = fields.Many2one(
        comodel_name='product.product',
        string='Categoría de gasto de origen',
        required=True, ondelete='cascade',
        domain="[('can_be_expensed', '=', True)]",
    )
    origin_company_id = fields.Many2one(related='origin_product_id.company_id', string='Empresa de origen')
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto en esta empresa',
        required=True, ondelete='restrict', check_company=True,
        domain="[('purchase_ok', '=', True)]",
        help='De él toma la línea de la factura la cuenta de gasto, los impuestos y el tipo de operación de detracción.',
    )

    _sql_constraints = [
        ('origin_uniq', 'unique(company_id, origin_product_id)',
         'La categoría de gasto ya tiene un producto equivalente en esta empresa.'),
    ]
