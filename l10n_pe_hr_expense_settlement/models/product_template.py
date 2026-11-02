from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_pe_is_advance_refund = fields.Boolean(
        string='Devolución de entrega a rendir',
        help='Categoría para registrar en el informe de gastos el sobrante del anticipo que el '
             'empleado devuelve: no genera factura sino un cobro en el banco o la caja elegidos.',
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _l10n_pe_get_expense_taxes(self, company):
        """Impuestos que propone la categoría en un gasto de la compañía. Una
        devolución no lleva impuestos."""
        self.ensure_one()
        if self.l10n_pe_is_advance_refund:
            return self.env['account.tax']
        return self.supplier_taxes_id.filtered_domain(self.env['account.tax']._check_company_domain(company))
