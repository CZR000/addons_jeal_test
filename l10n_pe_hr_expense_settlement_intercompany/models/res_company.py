from odoo import fields, models

# Cuentas por defecto (plan contable del grupo): moneda nacional / extranjera.
DEFAULT_IC_ACCOUNTS = {
    'receivable': ('1699000', '1699001'),
    'payable': ('4699000', '4699001'),
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    hr_expense_ic_receive = fields.Boolean(
        string='Puede recibir gastos de otras empresas',
        help='Los empleados de otras empresas del grupo pueden rendir comprobantes emitidos a esta '
             'empresa: se le crea una factura de proveedor en borrador para que la contadora la revise.',
    )
    hr_expense_ic_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de los gastos recibidos',
        check_company=True,
        domain="[('type', '=', 'purchase')]",
        help='Diario de compras de las facturas en borrador de gastos rendidos en otras empresas. '
             'Vacío: el diario de gastos de la compañía o el primer diario de compras.',
    )
    hr_expense_ic_receivable_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta por cobrar intercompany M.N.',
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
        help='Gasto que pagó un empleado de esta empresa con un comprobante de otra empresa del grupo. '
             'Vacío: 1699000.',
    )
    hr_expense_ic_receivable_foreign_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta por cobrar intercompany M.E.',
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
        help='Lo mismo para los gastos en moneda extranjera. Vacío: 1699001.',
    )
    hr_expense_ic_payable_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta por pagar intercompany M.N.',
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
        help='Deuda con la empresa del grupo que pagó un gasto de esta empresa. Vacío: 4699000.',
    )
    hr_expense_ic_payable_foreign_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta por pagar intercompany M.E.',
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
        help='Lo mismo para los gastos en moneda extranjera. Vacío: 4699001.',
    )

    hr_expense_ic_default_product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto por defecto de los gastos recibidos',
        check_company=True,
        domain="[('purchase_ok', '=', True)]",
        help='Producto de la línea de la factura en borrador cuando el producto del gasto no existe en esta empresa '
             'y no hay equivalencia para su categoría.',
    )

    def _get_hr_expense_ic_account(self, kind, currency):
        """Cuenta intercompany por cobrar ('receivable') o por pagar ('payable') de
        una moneda: la configurada o, si no hay, la del plan del grupo."""
        self.ensure_one()
        foreign = currency != self.currency_id
        account = self[f"hr_expense_ic_{kind}_{'foreign_' if foreign else ''}account_id"]
        if account:
            return account
        code = DEFAULT_IC_ACCOUNTS[kind][1 if foreign else 0]
        # El código de la cuenta depende de la compañía activa: se busca en la de self
        # (al rendir en OMNI se busca la cuenta por pagar de la otra empresa).
        return self.env['account.account'].with_company(self).sudo().search([
            *self.env['account.account']._check_company_domain(self),
            ('code', '=', code),
        ], limit=1)

    def _get_hr_expense_ic_product(self, expense_product):
        """Producto de esta empresa para un gasto de otra: el mismo si es compartido
        (o de esta empresa), uno con el mismo código, el de la tabla de
        equivalencias o el por defecto. Devuelve (producto, origen)."""
        self.ensure_one()
        Product = self.env['product.product'].sudo()
        if not expense_product:
            return Product, False
        if expense_product.company_id in (self, self.env['res.company']):
            return expense_product, 'same'
        if expense_product.default_code:
            product = Product.search([
                *Product._check_company_domain(self),
                ('default_code', '=', expense_product.default_code),
                ('purchase_ok', '=', True),
            ], limit=1)
            if product:
                return product, 'code'
        equivalence = self.env['hr.expense.ic.product'].sudo().search([
            ('company_id', '=', self.id),
            ('origin_product_id', '=', expense_product.id),
        ], limit=1)
        if equivalence:
            return equivalence.product_id, 'equivalence'
        if self.hr_expense_ic_default_product_id:
            return self.hr_expense_ic_default_product_id, 'default'
        return Product, False

    def _get_hr_expense_ic_journal(self):
        self.ensure_one()
        return (
            self.hr_expense_ic_journal_id
            or self.expense_journal_id
            or self.env['account.journal'].sudo().search([
                *self.env['account.journal']._check_company_domain(self),
                ('type', '=', 'purchase'),
            ], limit=1)
        )
