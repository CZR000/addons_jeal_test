from odoo import api, fields, models, Command, _
from odoo.exceptions import ValidationError


class HrExpenseLine(models.Model):
    _name = 'hr.expense.line'
    _description = 'Línea adicional de gasto'
    _inherit = ['analytic.mixin']
    _order = 'sequence, id'

    expense_id = fields.Many2one(
        'hr.expense',
        string='Gasto',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        domain=[('can_be_expensed', '=', True)],
    )
    # 'name' se usa internamente para el asiento pero no se muestra en la vista
    name = fields.Char('Descripción')
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta Contable',
        domain=[('deprecated', '=', False), ('account_type', 'not in', ['asset_receivable', 'liability_payable'])],
    )
    # analytic_distribution viene de analytic.mixin
    quantity = fields.Float('Cantidad', default=1.0, digits=(16, 2))
    price_unit = fields.Float('Precio unitario', digits='Product Price')
    tax_ids = fields.Many2many(
        'account.tax',
        string='Impuestos',
        domain=[('type_tax_use', 'in', ['purchase', 'none'])],
    )
    currency_id = fields.Many2one(related='expense_id.currency_id', store=True)
    company_id = fields.Many2one(related='expense_id.company_id', store=True)
    price_subtotal = fields.Monetary('Subtotal', compute='_compute_amounts', store=True)
    price_total = fields.Monetary('Total', compute='_compute_amounts', store=True)

    @api.depends('quantity', 'price_unit', 'tax_ids', 'currency_id')
    def _compute_amounts(self):
        for line in self:
            if line.tax_ids:
                taxes = line.tax_ids.compute_all(
                    line.price_unit,
                    currency=line.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                )
                line.price_subtotal = taxes['total_excluded']
                line.price_total = taxes['total_included']
            else:
                line.price_subtotal = line.quantity * line.price_unit
                line.price_total = line.price_subtotal

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return
        self.name = self.product_id.display_name
        accounts = self.product_id.product_tmpl_id._get_product_accounts()
        if accounts.get('expense'):
            self.account_id = accounts['expense']
        self.tax_ids = self.product_id.supplier_taxes_id.filtered(
            lambda t: t.company_id == self.company_id
        )

    # ------------------------------------------------------------------
    # Analítica obligatoria en cuentas marcadas con "Usar Cuentas de Destino"
    # (mismo mecanismo que account_analytic_warning_wizard aplica a account.move)
    # ------------------------------------------------------------------
    @api.constrains('account_id', 'analytic_distribution')
    def _check_analytic_required_for_destination_account(self):
        for line in self:
            account = line.account_id
            if not account:
                continue
            if 'has_destination_account' in account._fields and account.has_destination_account \
                    and not line.analytic_distribution:
                raise ValidationError(_(
                    'La Distribución Analítica es obligatoria para la cuenta "%s" '
                    '(configurada con "Usar Cuentas de Destino").'
                ) % account.display_name)

    def _prepare_move_line_vals(self):
        """Prepara vals de línea contable para creación de asiento."""
        self.ensure_one()
        expense = self.expense_id
        account = self.account_id
        if not account and self.product_id:
            account = self.product_id.product_tmpl_id._get_product_accounts().get('expense')

        # Partner: usa vendor_id del gasto padre si está configurado
        if expense.payment_mode == 'company_account':
            partner_id = False
        elif hasattr(expense, 'vendor_id') and expense.vendor_id:
            partner_id = expense.vendor_id.id
        else:
            partner_id = expense.employee_id.sudo().work_contact_id.id

        return {
            'name': f'{expense.employee_id.name}: {self.name or self.product_id.display_name}',
            'account_id': account.id if account else False,
            'quantity': self.quantity or 1,
            'price_unit': self.price_unit,
            'product_id': self.product_id.id,
            'analytic_distribution': self.analytic_distribution,
            'expense_id': expense.id,
            'partner_id': partner_id,
            'tax_ids': [Command.set(self.tax_ids.ids)],
        }
