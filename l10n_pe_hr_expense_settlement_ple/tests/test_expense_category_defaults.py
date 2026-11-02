from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.l10n_pe_hr_expense_settlement.tests.common import TestExpenseSettlementCommon


@tagged('post_install', '-at_install')
class TestExpenseCategoryDefaults(TestExpenseSettlementCommon):
    """P3 y P4 de la prueba en OMNI del 05/10/2026: asignación de IGV y
    clasificación (tabla 30) desde la categoría, e importes sin IGV en el RCE."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax_gdg = cls.create_igv_tax('IGV gravadas', 18.0, 'P_BASE_GDG', sequence=5)
        cls.tax_gdg_10 = cls.create_igv_tax('IGV 10% gravadas', 10.0, 'P_BASE_GDG', sequence=6)
        cls.tax_gdm = cls.create_igv_tax('IGV gravadas y no gravadas', 18.0, 'P_BASE_GDM')
        cls.tax_gdng = cls.create_igv_tax('IGV no gravadas', 18.0, 'P_BASE_GDNG')
        cls.tax_ng = cls.create_igv_tax('Inafecto', 0.0, 'P_BASE_NG')
        cls.classification_4 = cls.env['classification.services'].search([('code', '=', '4')], limit=1) \
            or cls.env['classification.services'].create({'code': '4', 'description': 'Otros servicios'})
        cls.mobility = cls.env['product.product'].create({
            'name': 'Movilidad',
            'can_be_expensed': True,
            'supplier_taxes_id': [Command.set(cls.tax_purchase_a.ids)],
            'l10n_pe_igv_assignment': 'ng',
            'l10n_pe_classification_id': cls.classification_4.id,
        })

    @classmethod
    def get_tax_tag(cls, name):
        Tag = cls.env['account.account.tag']
        return Tag.search([('name', '=', name), ('applicability', '=', 'taxes')], limit=1) or Tag.create({
            'name': name, 'applicability': 'taxes', 'country_id': cls.company.account_fiscal_country_id.id,
        })

    @classmethod
    def create_igv_tax(cls, name, amount, base_tag, sequence=10):
        tax_tag = base_tag.replace('BASE', 'TAX')

        def repartition(sign):
            tax_tags = cls.get_tax_tag(f'{sign}{tax_tag}') if amount and tax_tag != 'P_TAX_NG' else cls.env['account.account.tag']
            return [
                Command.create({'repartition_type': 'base', 'tag_ids': [Command.set(cls.get_tax_tag(f'{sign}{base_tag}').ids)]}),
                Command.create({'repartition_type': 'tax', 'tag_ids': [Command.set(tax_tags.ids)]}),
            ]
        return cls.env['account.tax'].create({
            'name': name,
            'amount': amount,
            'amount_type': 'percent',
            'type_tax_use': 'purchase',
            'sequence': sequence,
            'company_id': cls.company.id,
            'invoice_repartition_line_ids': repartition('+'),
            'refund_repartition_line_ids': repartition('-'),
        })

    def mobility_values(self, amount, **values):
        """Gasto de "Movilidad" con los impuestos que propone la categoría."""
        values = self.receipt_values(amount, product_id=self.mobility.id, **values)
        values.pop('tax_ids')
        return values

    # -------------------------------------------------------------------------
    # P3. Asignación de IGV y clasificación desde la categoría
    # -------------------------------------------------------------------------

    def test_igv_assignment_chooses_the_tax(self):
        category = self.mobility
        expected = {'gdg': self.tax_gdg, 'gdm': self.tax_gdm, 'gdng': self.tax_gdng, 'ng': self.tax_ng}
        for assignment, tax in expected.items():
            category.l10n_pe_igv_assignment = assignment
            expense = self.env['hr.expense'].create(self.mobility_values(100.0))
            self.assertEqual(expense.tax_ids, tax, assignment)

    def test_igv_assignment_prefers_the_category_tax(self):
        """Una categoría con IGV de 10% (restaurantes) conserva ese impuesto."""
        self.mobility.write({'l10n_pe_igv_assignment': 'gdg', 'supplier_taxes_id': [Command.set(self.tax_gdg_10.ids)]})
        with Form(self.env['hr.expense'].with_context(default_employee_id=self.expense_employee.id)) as expense_form:
            expense_form.product_id = self.mobility
            self.assertEqual(expense_form.tax_ids[:], self.tax_gdg_10)
            expense_form.l10n_pe_in_purchase_register = False

    def test_without_assignment_the_category_taxes_are_used(self):
        self.mobility.l10n_pe_igv_assignment = False
        with Form(self.env['hr.expense'].with_context(default_employee_id=self.expense_employee.id)) as expense_form:
            expense_form.product_id = self.mobility
            self.assertEqual(expense_form.tax_ids[:], self.tax_purchase_a)
            expense_form.l10n_pe_in_purchase_register = False

    def test_bill_takes_the_category_defaults(self):
        """Factura generada desde un gasto de "Movilidad": clasificación 4 y sin IGV."""
        with Form(self.env['hr.expense'].with_context(default_employee_id=self.expense_employee.id)) as expense_form:
            expense_form.product_id = self.mobility
            expense_form.total_amount_currency = 40.0
            expense_form.vendor_id = self.vendor
            expense_form.l10n_pe_document_type_id = self.document_type_invoice
            expense_form.l10n_pe_document_series = 'F001'
            expense_form.l10n_pe_document_number = '9'
        expense = expense_form.record
        bill = self.approve_and_post(self.env['hr.expense.sheet'].create({
            'name': 'Movilidad', 'employee_id': self.expense_employee.id,
            'expense_line_ids': [Command.set(expense.ids)],
        }))
        self.assertRecordValues(bill, [{'types_goods_services_id': self.classification_4.id, 'amount_tax': 0.0}])
        self.assertEqual(bill.invoice_line_ids.tax_ids, self.tax_ng)

    def test_bill_classification_of_the_main_line(self):
        services = self.env['classification.services'].search([('code', '=', '5')], limit=1) \
            or self.env['classification.services'].create({'code': '5', 'description': 'Otros'})
        other_category = self.env['product.product'].create({
            'name': 'Hospedaje', 'can_be_expensed': True, 'l10n_pe_classification_id': services.id,
        })
        bill = self.approve_and_post(self.create_sheet([
            self.mobility_values(30.0, number='7'),
            self.receipt_values(70.0, number='7', product_id=other_category.id),
        ]))
        self.assertEqual(len(bill), 1)
        self.assertEqual(bill.types_goods_services_id, services, 'La de la línea de mayor importe')

    def test_split_line_takes_the_assignment_of_its_category(self):
        self.mobility.l10n_pe_igv_assignment = 'ng'
        expense = self.env['hr.expense'].create(self.receipt_values(
            150.0, number='78', tax_ids=[Command.set(self.tax_gdg.ids)],
        ))
        wizard = self.env['hr.expense.split.wizard'].browse(expense.action_split_wizard()['res_id'])
        with Form(wizard) as wizard_form:
            with wizard_form.expense_split_line_ids.edit(1) as line:
                line.product_id = self.mobility
        self.assertEqual(wizard.expense_split_line_ids[1].tax_ids, self.tax_ng)

    # -------------------------------------------------------------------------
    # P4. Registro de Compras: importes sin IGV como adquisiciones no gravadas
    # -------------------------------------------------------------------------

    def tax_data(self, bill):
        self.env.flush_all()
        self.env.cr.execute('SELECT get_tax_purchase(%s, %s)::text', [bill.id, bill.move_type])
        values = self.env.cr.fetchone()[0].strip('()').split(',')
        return dict(zip(
            ['base_gdg', 'tax_gdg', 'base_gdm', 'tax_gdm', 'base_gdng', 'tax_gdng', 'base_ng',
             'isc', 'icbp', 'other', 'total'],
            [float(value) for value in values],
        ))

    def test_untaxed_lines_are_reported_as_not_taxed(self):
        """F001-99105 de OMNI: 200 con IGV + 154 sin impuesto = 354."""
        bill = self.approve_and_post(self.create_sheet([
            self.receipt_values(200.0, number='99105', tax_ids=[Command.set(self.tax_gdg.ids)]),
            self.receipt_values(154.0, number='99105'),
        ]))
        data = self.tax_data(bill)
        self.assertAlmostEqual(data['base_gdg'], 169.49)
        self.assertAlmostEqual(data['tax_gdg'], 30.51)
        self.assertAlmostEqual(data['base_ng'], 154.0)
        self.assertAlmostEqual(sum(list(data.values())[:10]), bill.amount_total)

    def test_bill_without_any_tax_is_fully_reported(self):
        """F001-32656598: comprobante sin impuesto que salía con total 0.00."""
        bill = self.create_receipt_bill(300.0, number='32656598')
        data = self.tax_data(bill)
        self.assertAlmostEqual(data['base_ng'], 300.0)
        self.assertAlmostEqual(sum(list(data.values())[:10]), 300.0)

    def test_untaxed_refund_is_negative(self):
        sheet = self.create_sheet([self.receipt_values(50.0, number='31')])
        bill = self.approve_and_post(sheet)
        # Nota de crédito de la factura del comprobante (restablecer el informe la anula).
        refund = bill._reverse_moves([{'invoice_date': bill.invoice_date}], cancel=True)
        self.assertEqual(refund.move_type, 'in_refund')
        self.assertAlmostEqual(self.tax_data(refund)['base_ng'], -50.0)
