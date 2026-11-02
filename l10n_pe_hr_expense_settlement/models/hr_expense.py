import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import groupby

# Correlativo SUNAT de los comprobantes electrónicos: se completa con ceros a
# la izquierda, igual que la referencia de las facturas de compra de jeal.
DOCUMENT_NUMBER_PADDING = 8

# Descripciones que delatan dinero devuelto por el empleado registrado con una
# categoría de gasto (devolución, devuelve, reintegro, sobrante...).
ADVANCE_REFUND_HINT = re.compile(r'devol|devuel|reintegr|sobrante', re.IGNORECASE)


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    l10n_pe_available_document_type_ids = fields.Many2many(
        comodel_name='l10n_latam.document.type',
        compute='_compute_l10n_pe_available_document_type_ids',
    )
    l10n_pe_document_type_id = fields.Many2one(
        comodel_name='l10n_latam.document.type',
        string='Tipo de documento',
        domain="[('id', 'in', l10n_pe_available_document_type_ids)]",
        help='Tipo de comprobante SUNAT (Factura, Boleta, Ticket...). Viaja a la factura de proveedor.',
    )
    l10n_pe_document_series = fields.Char(string='Serie', help='Serie del comprobante, p.ej. F001.')
    l10n_pe_document_number = fields.Char(string='Número', help='Correlativo del comprobante, p.ej. 1234.')
    l10n_pe_document_reference = fields.Char(
        string='Comprobante',
        compute='_compute_l10n_pe_document_reference',
        store=True,
        index='btree_not_null',
        help='SERIE-NÚMERO tal como se registra en la referencia de la factura de proveedor, '
             'que es lo que leen el PLE 8.1 y el SIRE.',
    )
    payment_mode = fields.Selection(
        help='Para rendir un anticipo o pedir reembolso elija "Empleado": se piden los datos del '
             'comprobante y se liquida contra la cuenta 14. Con "Compañía" no se piden esos datos '
             'ni se liquida contra la 14.',
    )
    l10n_pe_in_purchase_register = fields.Boolean(
        string='Va al Registro de Compras',
        default=True,
        help='Marcado: el comprobante va al Registro de Compras y se exigen el proveedor, el tipo '
             'de documento, la serie y el número. Desmárquelo para gastos sin comprobante válido '
             '(p.ej. movilidad sin sustento): se registran en el diario de comprobantes fuera del '
             'Registro de Compras, excluido del PLE y del SIRE, y se liquidan igual contra la 14.',
    )
    l10n_pe_receipt_total_amount = fields.Monetary(
        string='Total del comprobante',
        currency_field='currency_id',
        copy=False,
        help='Total del comprobante que se dividió en varias líneas con "Dividir gasto": las '
             'líneas del comprobante deben sumar este total.',
    )
    l10n_pe_split_origin_id = fields.Many2one(
        comodel_name='hr.expense',
        string='Dividido de',
        readonly=True,
        copy=False,
        index='btree_not_null',
        help='Gasto original del que salió esta línea con "Dividir gasto".',
    )
    # Devolución del sobrante del anticipo (no es un gasto: genera un cobro).
    l10n_pe_is_advance_refund = fields.Boolean(related='product_id.l10n_pe_is_advance_refund')
    l10n_pe_refund_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Depositado en',
        check_company=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
        help='Banco donde el empleado depositó el sobrante, o la caja donde lo entregó en efectivo.',
    )
    l10n_pe_refund_payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Cobro de la devolución',
        readonly=True,
        copy=False,
    )
    l10n_pe_looks_like_refund = fields.Boolean(
        string='Parece una devolución',
        compute='_compute_l10n_pe_looks_like_refund',
        help='La descripción habla de dinero devuelto pero la categoría es de gasto: se '
             'registraría como una factura de compra y no como un cobro.',
    )

    @api.depends('product_id', 'company_id')
    def _compute_tax_ids(self):
        super()._compute_tax_ids()
        for expense in self.filtered('product_id'):
            expense.tax_ids = expense.product_id._l10n_pe_get_expense_taxes(expense.company_id)

    @api.depends('name', 'description', 'product_id', 'payment_mode')
    def _compute_l10n_pe_looks_like_refund(self):
        for expense in self:
            expense.l10n_pe_looks_like_refund = (
                expense.payment_mode == 'own_account'
                and not expense.l10n_pe_is_advance_refund
                and bool(ADVANCE_REFUND_HINT.search(f'{expense.name or ""} {expense.description or ""}'))
            )

    @api.constrains('product_id', 'payment_mode', 'vendor_id')
    def _check_l10n_pe_advance_refund(self):
        for expense in self.filtered('l10n_pe_is_advance_refund'):
            if expense.payment_mode != 'own_account':
                raise ValidationError(_(
                    'La devolución "%s" la hace el empleado: use "Pagado por: Empleado".', expense.name,
                ))
            if expense.vendor_id:
                raise ValidationError(_(
                    'La devolución "%s" no lleva proveedor ni comprobante.', expense.name,
                ))

    @api.depends('company_id', 'vendor_id')
    def _compute_l10n_pe_available_document_type_ids(self):
        for expense in self:
            expense.l10n_pe_available_document_type_ids = self.env['l10n_latam.document.type'].search(
                expense._l10n_pe_get_document_types_domain()
            )

    def _l10n_pe_get_document_types_domain(self):
        """Tipos de comprobante que acepta la factura de este gasto. Los módulos
        puente agregan las reglas de la localización instalada."""
        self.ensure_one()
        return [('country_id', '=', self.company_id.account_fiscal_country_id.id)]

    def _l10n_pe_is_rendered_expense(self):
        """Gasto que el empleado rinde con su comprobante (o sin él): se registra
        como factura de compra y se liquida contra la 14."""
        self.ensure_one()
        return self.payment_mode == 'own_account' and not self.l10n_pe_is_advance_refund

    def _l10n_pe_get_missing_receipt_data(self):
        """Datos del comprobante que exige el Registro de Compras y le faltan al
        gasto. Fuera del Registro de Compras no se exige ninguno."""
        self.ensure_one()
        if not self.l10n_pe_in_purchase_register:
            return []
        required = [
            (_('proveedor'), self.vendor_id),
            (_('tipo de documento'), self.l10n_pe_document_type_id),
            (_('serie'), self.l10n_pe_document_series),
            (_('número'), self.l10n_pe_document_number),
        ]
        return [label for label, value in required if not value]

    @api.depends('l10n_pe_document_series', 'l10n_pe_document_number')
    def _compute_l10n_pe_document_reference(self):
        for expense in self:
            series = self._l10n_pe_normalize_document_series(expense.l10n_pe_document_series)
            number = self._l10n_pe_normalize_document_number(expense.l10n_pe_document_number)
            expense.l10n_pe_document_reference = f'{series}-{number}' if series and number else False

    @api.model
    def _l10n_pe_normalize_document_series(self, series):
        return (series or '').strip().upper()

    @api.model
    def _l10n_pe_normalize_document_number(self, number):
        number = (number or '').strip()
        return number.zfill(DOCUMENT_NUMBER_PADDING) if number.isdigit() else number

    @api.onchange('l10n_pe_document_series', 'l10n_pe_document_number')
    def _onchange_l10n_pe_document(self):
        for expense in self:
            expense.l10n_pe_document_series = self._l10n_pe_normalize_document_series(expense.l10n_pe_document_series)
            expense.l10n_pe_document_number = self._l10n_pe_normalize_document_number(expense.l10n_pe_document_number)

    @api.constrains('l10n_pe_document_series', 'l10n_pe_document_number')
    def _check_l10n_pe_document(self):
        # El PLE separa serie y número por el guion de la referencia: ninguno
        # de los dos puede contener guiones ni espacios.
        for expense in self:
            for label, value in ((_('serie'), expense.l10n_pe_document_series),
                                 (_('número'), expense.l10n_pe_document_number)):
                if value and not value.strip().isalnum():
                    raise ValidationError(_(
                        'El %(label)s del comprobante "%(value)s" del gasto "%(expense)s" solo puede '
                        'contener letras y números (sin guiones ni espacios).',
                        label=label, value=value, expense=expense.name,
                    ))

    @api.depends('product_id', 'account_id', 'employee_id')
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for expense in self:
            employee_distribution = expense.employee_id.sudo().expense_analytic_distribution
            if employee_distribution:
                expense.analytic_distribution = employee_distribution

    # -------------------------------------------------------------------------
    # Factura de proveedor por comprobante
    # -------------------------------------------------------------------------

    def _l10n_pe_is_vendor_receipt(self):
        """Gasto reembolsable respaldado por el comprobante de un proveedor real:
        se registra como su propia factura de proveedor en vez de sumarse a la
        factura nativa a nombre del empleado."""
        self.ensure_one()
        return self.payment_mode == 'own_account' and bool(self.vendor_id) and not self.l10n_pe_is_advance_refund

    def _l10n_pe_get_receipt_key(self):
        """Gastos con la misma clave son líneas de un mismo comprobante (p.ej. los
        generados con "Dividir gasto") y van juntos en una sola factura."""
        self.ensure_one()
        return (
            self.vendor_id.id,
            self.l10n_pe_document_type_id.id,
            self.l10n_pe_document_reference or f'expense-{(self.l10n_pe_split_origin_id or self).id}',
            self.currency_id.id,
            self.l10n_pe_in_purchase_register,
        )

    def _l10n_pe_check_receipt_data(self):
        missing = [
            (expense, labels)
            for expense in self.filtered(lambda expense: expense._l10n_pe_is_rendered_expense())
            if (labels := expense._l10n_pe_get_missing_receipt_data())
        ]
        if missing:
            raise UserError(_(
                'Los siguientes gastos van al Registro de Compras y les faltan datos del comprobante '
                '(complételos o desmarque "Va al Registro de Compras" si no tienen comprobante válido):\n%s',
                '\n'.join(f'- {expense.name}: {", ".join(labels)}' for expense, labels in missing),
            ))
        receipts = self.filtered(lambda expense: expense._l10n_pe_is_vendor_receipt())
        unbalanced = receipts._l10n_pe_get_unbalanced_receipts()
        if unbalanced:
            raise UserError(_(
                'Las líneas de los siguientes comprobantes no suman su total:\n%s',
                '\n'.join(
                    f'- {expenses[0].l10n_pe_document_reference or expenses[0].name}: '
                    f'{expenses[0].currency_id.format(sum(expenses.mapped("total_amount_currency")))} '
                    f'/ {expenses[0].currency_id.format(total)}'
                    for expenses, total in unbalanced
                ),
            ))
        duplicated = receipts._l10n_pe_get_duplicated_receipts()
        if duplicated:
            raise UserError(_(
                'Los siguientes comprobantes ya fueron rendidos o registrados:\n%s',
                '\n'.join(f'- {expense.name}: {expense.l10n_pe_document_reference} ({expense.vendor_id.display_name}) '
                          f'-> {document.display_name}' for expense, document in duplicated),
            ))
        not_allowed = receipts.filtered(lambda expense: (
            expense.l10n_pe_document_type_id
            and expense.l10n_pe_document_type_id not in expense.l10n_pe_available_document_type_ids
        ))
        if not_allowed:
            raise UserError(_(
                'El tipo de documento no está permitido para el proveedor de los siguientes gastos:\n%s',
                '\n'.join(
                    f'- {expense.name}: {expense.l10n_pe_document_type_id.display_name} ({expense.vendor_id.display_name})'
                    for expense in not_allowed
                ),
            ))

    def _l10n_pe_get_unbalanced_receipts(self):
        """Comprobantes divididos en líneas cuya suma ya no es el total del
        comprobante (p.ej. se editó o borró una línea después de dividir).

        :return: lista de (líneas del comprobante, total del comprobante)
        """
        unbalanced = []
        for _key, expenses in groupby(self, key=lambda expense: (expense.sheet_id.id, expense._l10n_pe_get_receipt_key())):
            expenses = self.browse().union(*expenses)
            total = max(expenses.mapped('l10n_pe_receipt_total_amount'))
            currency = expenses[0].currency_id
            if total and currency.compare_amounts(sum(expenses.mapped('total_amount_currency')), total):
                unbalanced.append((expenses, total))
        return unbalanced

    def _l10n_pe_get_duplicated_receipts(self):
        """Comprobantes ya rendidos en otro informe vigente o ya registrados como
        factura de proveedor. Varios gastos del mismo informe sí pueden compartir
        comprobante (líneas de un mismo comprobante, p.ej. con "Dividir gasto").

        :return: lista de (gasto, documento con el que choca)
        """
        duplicated = []
        for expense in self.filtered('l10n_pe_document_reference'):
            receipt_domain = [
                ('company_id', '=', expense.company_id.id),
                ('l10n_pe_document_type_id', '=', expense.l10n_pe_document_type_id.id),
                ('l10n_pe_document_reference', '=', expense.l10n_pe_document_reference),
                ('vendor_id.commercial_partner_id', '=', expense.vendor_id.commercial_partner_id.id),
            ]
            other_expense = self.search([
                *receipt_domain,
                ('sheet_id', '!=', False),
                ('sheet_id', '!=', expense.sheet_id.id),
                ('sheet_id.state', 'not in', ('draft', 'cancel')),
            ], limit=1)
            if other_expense:
                duplicated.append((expense, other_expense.sheet_id))
                continue
            bill = self.env['account.move'].search([
                ('company_id', '=', expense.company_id.id),
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('state', '!=', 'cancel'),
                ('payment_state', '!=', 'reversed'),
                ('commercial_partner_id', '=', expense.vendor_id.commercial_partner_id.id),
                ('l10n_latam_document_type_id', '=', expense.l10n_pe_document_type_id.id),
                ('ref', '=', expense.l10n_pe_document_reference),
            ], limit=1)
            if bill:
                duplicated.append((expense, bill))
        return duplicated

    def _l10n_pe_is_done_without_bill(self):
        """La línea quedó registrada sin factura en la empresa del informe (p.ej. la
        devolución del sobrante, con su cobro publicado)."""
        self.ensure_one()
        return self.l10n_pe_is_advance_refund and self.l10n_pe_refund_payment_id.move_id.state == 'posted'

    def _prepare_move_lines_vals(self):
        vals = super()._prepare_move_lines_vals()
        if self._l10n_pe_is_vendor_receipt():
            vals['partner_id'] = self.vendor_id.id
            # La factura del comprobante va en su moneda original (la nativa
            # siempre convierte a la moneda de la compañía).
            vals['price_unit'] = self.total_amount_currency / (self.quantity or 1.0)
        return vals
