from odoo import api, fields, models

# Destino del IGV de la adquisición (columnas del Registro de Compras) y etiqueta
# de la base imponible que llevan los impuestos de compra de la localización.
IGV_ASSIGNMENTS = [
    ('gdg', 'Gravada: destino operaciones gravadas (con crédito fiscal)'),
    ('gdm', 'Gravada: destino operaciones gravadas y no gravadas'),
    ('gdng', 'Gravada: destino operaciones no gravadas (sin crédito fiscal)'),
    ('ng', 'No gravada (exonerada o inafecta)'),
]
IGV_ASSIGNMENT_BASE_TAGS = {
    'gdg': 'P_BASE_GDG',
    'gdm': 'P_BASE_GDM',
    'gdng': 'P_BASE_GDNG',
    'ng': 'P_BASE_NG',
}


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_pe_igv_assignment = fields.Selection(
        selection=IGV_ASSIGNMENTS,
        string='Asignación de IGV',
        help='Destino del IGV de los gastos de esta categoría: define el impuesto que se propone '
             'en el gasto (y en su factura de compra) y la columna del Registro de Compras. Vacío: '
             'se usan los impuestos de proveedor de la categoría.',
    )
    l10n_pe_classification_id = fields.Many2one(
        comodel_name='classification.services',
        string='Clasificación de bienes y servicios',
        help='Clasificación de los bienes y servicios adquiridos (tabla 30 SUNAT) que llevan las '
             'facturas de compra generadas desde gastos de esta categoría.',
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _l10n_pe_get_expense_taxes(self, company):
        taxes = super()._l10n_pe_get_expense_taxes(company)
        if not self.l10n_pe_igv_assignment or self.l10n_pe_is_advance_refund:
            return taxes
        return self._l10n_pe_get_igv_assignment_tax(company) or taxes

    def _l10n_pe_get_igv_assignment_tax(self, company):
        """Impuesto de compra de la compañía con la base imponible de la asignación
        de IGV: el de la categoría si ya tiene uno así (p.ej. un IGV de 10%) o, si
        no, el primero de la compañía (sin precio incluido, por secuencia)."""
        self.ensure_one()
        tag = IGV_ASSIGNMENT_BASE_TAGS[self.l10n_pe_igv_assignment]
        Tax = self.env['account.tax'].with_company(company)
        domain = [
            *Tax._check_company_domain(company),
            ('type_tax_use', '=', 'purchase'),
            ('amount_type', '=', 'percent'),
            ('amount', '=' if self.l10n_pe_igv_assignment == 'ng' else '>', 0.0),
            ('invoice_repartition_line_ids', 'any', [
                ('repartition_type', '=', 'base'),
                ('tag_ids.name', 'in', [tag, f'+{tag}']),
            ]),
        ]
        own_taxes = self.supplier_taxes_id.filtered_domain(domain)
        if own_taxes:
            return own_taxes.sorted(lambda tax: (tax.sequence, tax.id))[:1]
        return Tax.search(domain).filtered(lambda tax: not tax.price_include).sorted(
            lambda tax: (tax.sequence, tax.id)
        )[:1]

    @api.model
    def _get_expense_classification(self, expenses):
        """Clasificación de la factura de un comprobante: la de la categoría de la
        línea de mayor importe que tenga una."""
        classified = expenses.filtered('product_id.l10n_pe_classification_id')
        main = max(classified, key=lambda expense: expense.total_amount, default=expenses.browse())
        return main.product_id.l10n_pe_classification_id
