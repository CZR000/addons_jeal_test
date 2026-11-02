# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrExpenseLine(models.Model):
    """Detalle del comprobante de un gasto.

    Se usa cuando ``hr.expense.use_multiple_lines = True`` para desglosar
    el comprobante por líneas (múltiples productos / cuentas contables /
    distribuciones analíticas dentro de una sola factura de proveedor).
    """

    _name = 'hr.expense.line'
    _inherit = ['analytic.mixin']
    _description = 'Línea del comprobante del gasto'
    _order = 'expense_id, sequence, id'

    expense_id = fields.Many2one(
        comodel_name='hr.expense',
        string='Gasto',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Secuencia', default=10)

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto',
        required=True,
        domain="[('can_be_expensed', '=', True)]",
    )
    name = fields.Char(
        string='Descripción',
        compute='_compute_name',
        store=True,
        readonly=False,
        required=True,
    )
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta contable',
        compute='_compute_account_id',
        store=True,
        readonly=False,
        domain="[('deprecated', '=', False)]",
    )
    quantity = fields.Float(
        string='Cantidad',
        default=1.0,
        digits='Product Unit of Measure',
    )
    price_unit = fields.Float(string='Precio unitario', digits='Product Price')
    tax_ids = fields.Many2many(
        comodel_name='account.tax',
        string='Impuestos',
        domain="[('type_tax_use', 'in', ('purchase', 'none'))]",
    )

    company_id = fields.Many2one(
        related='expense_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='expense_id.currency_id',
        store=True,
        readonly=True,
    )

    price_subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    price_total = fields.Monetary(
        string='Total',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('product_id')
    def _compute_name(self):
        for line in self:
            if line.product_id and not line.name:
                line.name = line.product_id.display_name

    @api.depends('product_id', 'company_id')
    def _compute_account_id(self):
        """Fallback de cuenta contable desde el producto."""
        for line in self:
            if not line.product_id:
                continue
            product = line.product_id.with_company(line.company_id)
            account = (
                product.property_account_expense_id
                or product.categ_id.property_account_expense_categ_id
            )
            if account:
                line.account_id = account

    @api.depends('quantity', 'price_unit', 'tax_ids', 'currency_id')
    def _compute_amounts(self):
        """Cálculo vía ``taxes.compute_all`` cuando hay impuestos;
        multiplicación simple cuando no.
        """
        for line in self:
            if line.tax_ids:
                taxes = line.tax_ids.compute_all(
                    price_unit=line.price_unit,
                    currency=line.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=line.expense_id.vendor_id or False,
                )
                line.price_subtotal = taxes['total_excluded']
                line.price_total = taxes['total_included']
            else:
                subtotal = line.quantity * line.price_unit
                line.price_subtotal = subtotal
                line.price_total = subtotal

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _prepare_move_line_vals(self):
        """Prepara los vals para una línea de ``account.move`` a partir de
        esta línea del comprobante.

        Fallback de partner:
        ``vendor_id`` del padre → ``work_contact_id`` del empleado →
        ``False`` (caso ``company_account``).
        """
        self.ensure_one()
        expense = self.expense_id
        partner = (
            expense.vendor_id
            or expense.employee_id.work_contact_id
            or self.env['res.partner']
        )
        return {
            'name': self.name or (
                self.product_id.display_name if self.product_id else ''
            ),
            'product_id': self.product_id.id,
            'quantity': self.quantity,
            'price_unit': self.price_unit,
            'account_id': self.account_id.id,
            'tax_ids': [(6, 0, self.tax_ids.ids)],
            'analytic_distribution': self.analytic_distribution or False,
            'partner_id': partner.id if partner else False,
        }
