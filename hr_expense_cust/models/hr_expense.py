from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    # ------------------------------------------------------------------
    # New fields
    # ------------------------------------------------------------------
    reference = fields.Char(
        string='Referencia de factura',
        help='Formato SERIE-NUMERO, p.ej. F001-00012345. El número se '
             'autocompleta con ceros a la izquierda hasta 8 dígitos.',
    )
    l10n_latam_document_type_id = fields.Many2one(
        'l10n_latam.document.type',
        string='Tipo de documento',
        help='Tipo de documento (Factura, Boleta, etc.) para el registro de compras.',
    )
    include_in_purchase_register = fields.Boolean(
        string='Va al registro de compras',
        default=True,
        help=(
            'Indica si este gasto debe generar un asiento de tipo "Factura de proveedor" '
            'para aparecer en el registro de compras. '
            'Si está desmarcado, se generará como asiento contable genérico.'
        ),
    )

    # ------------------------------------------------------------------
    # Campos para líneas adicionales
    # ------------------------------------------------------------------
    use_extra_lines = fields.Boolean(
        string='Usar más líneas',
        default=False,
        help='Habilita una tabla de líneas adicionales para desglosar el gasto '
             'en varios conceptos con distintos productos/cuentas.',
    )
    extra_line_ids = fields.One2many(
        'hr.expense.line',
        'expense_id',
        string='Líneas adicionales',
    )

    # ------------------------------------------------------------------
    # price_unit depende de total_amount, que a su vez depende de
    # extra_line_ids - un registro hijo que no puede existir hasta que este
    # gasto ya tenga id. Por eso Odoo no puede precomputar price_unit en el
    # INSERT cuando use_extra_lines=True, y la columna (NOT NULL) rechaza el
    # INSERT si no se manda un valor. Se inyecta 0.0 solo en ese caso
    # puntual (nunca se pisa un price_unit ya definido) - poner un
    # default=0.0 directo en el campo rompía la creación de gastos
    # normales, porque interactúa mal con precompute en toda la clase.
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('use_extra_lines') and 'price_unit' not in vals:
                vals['price_unit'] = 0.0
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Extender _compute_amount para calcular total desde líneas extras
    # ------------------------------------------------------------------
    @api.depends('quantity', 'price_unit', 'tax_ids', 'currency_id',
                 'use_extra_lines', 'extra_line_ids.price_total')
    def _compute_total_amount(self):
        # Solo se toma el total de las líneas adicionales una vez que
        # existe al menos una: si el usuario recién marcó "Usar más líneas"
        # pero todavía no agregó ninguna, este cálculo forzaba total_amount
        # (y por dependencia, price_unit) a 0, y al guardar fallaba
        # "campo obligatorio" en price_unit. Mientras no haya líneas, se usa
        # el cálculo normal (respeta lo que el usuario ya haya escrito).
        extra_line_expenses = self.filtered(lambda e: e.use_extra_lines and e.extra_line_ids)
        regular_expenses = self - extra_line_expenses
        if regular_expenses:
            super(HrExpense, regular_expenses)._compute_total_amount()
        for expense in extra_line_expenses:
            expense.total_amount = sum(expense.extra_line_ids.mapped('price_total'))
            # price_unit depende de total_amount vía precompute, pero ese
            # precompute se rompe al sobreescribir _compute_total_amount
            # (no es una función precompute-compatible) - se fija acá mismo
            # para no depender de ese cálculo diferido.
            expense.price_unit = expense.total_amount / (expense.quantity or 1.0)

    # ------------------------------------------------------------------
    # Override _prepare_move_line_vals to carry vendor_id to move lines
    # ------------------------------------------------------------------
    def _prepare_move_lines_vals(self):
        vals = super()._prepare_move_lines_vals()
        if self.vendor_id:
            vals['partner_id'] = self.vendor_id.id
        return vals

    # ------------------------------------------------------------------
    # Override _get_expense_account_destination for company_account mode:
    # use the journal's configured account (payment_account_id on method line
    # or default_account_id) to generate the counter-entry.
    # This is already the standard behavior; keeping override to document intent.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Referencia de factura: SERIE-NUMERO, número de 8 dígitos
    # ------------------------------------------------------------------
    @api.onchange('reference')
    def _onchange_reference_pad(self):
        for expense in self:
            if expense.reference and '-' in expense.reference:
                serie, _sep, numero = expense.reference.rpartition('-')
                if numero.isdigit() and 0 < len(numero) < 8:
                    expense.reference = f"{serie}-{numero.zfill(8)}"

    @api.constrains('reference')
    def _check_reference_format(self):
        for expense in self.filtered('reference'):
            if '-' not in expense.reference:
                raise ValidationError(_(
                    'La referencia de factura debe tener el formato SERIE-NUMERO '
                    '(p.ej. F001-00012345): %s'
                ) % expense.reference)
            _serie, _sep, numero = expense.reference.rpartition('-')
            if not numero.isdigit() or len(numero) != 8:
                raise ValidationError(_(
                    'El número de la referencia de factura debe tener 8 dígitos '
                    '(p.ej. F001-00012345): %s'
                ) % expense.reference)

    # ------------------------------------------------------------------
    # Analítica obligatoria en cuentas marcadas con "Usar Cuentas de Destino"
    # (mismo mecanismo que account_analytic_warning_wizard aplica a account.move)
    # ------------------------------------------------------------------
    @api.constrains('account_id', 'analytic_distribution')
    def _check_analytic_required_for_destination_account(self):
        for expense in self:
            account = expense.account_id
            if 'has_destination_account' in account._fields and account.has_destination_account \
                    and not expense.analytic_distribution:
                raise ValidationError(_(
                    'La Distribución Analítica es obligatoria para la cuenta "%s" '
                    '(configurada con "Usar Cuentas de Destino").'
                ) % account.display_name)
