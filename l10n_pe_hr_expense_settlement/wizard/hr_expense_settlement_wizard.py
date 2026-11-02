from markupsafe import Markup

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError


class HrExpenseSettlementWizard(models.TransientModel):
    """Cancela la factura de un comprobante rendido contra los anticipos del
    empleado (cuenta 14) con un asiento de liquidación sin movimiento de caja:

        Debe  42 (proveedor de la factura)   monto aplicado
        Haber 14 (empleado, cada anticipo)   parte aplicada de cada anticipo
        Haber 14 (empleado, exceso)          lo rendido por encima del anticipo

    y concilia ambos lados. Se aplican los anticipos de la moneda de la factura
    (o el anticipo elegido en el informe). Entre la moneda de la factura y la de
    la compañía se usa el tipo de cambio de la factura, así la cuenta 42 se
    cancela por su saldo exacto; la diferencia contra el tipo de cambio de un
    anticipo en moneda extranjera la genera la conciliación nativa."""
    _name = 'hr.expense.settlement.wizard'
    _description = 'Conciliar factura de rendición con anticipo'
    _check_company_auto = True

    move_id = fields.Many2one('account.move', string='Factura', required=True, readonly=True)
    company_id = fields.Many2one(related='move_id.company_id')
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda de la compañía')
    currency_id = fields.Many2one(related='move_id.currency_id', string='Moneda')
    employee_id = fields.Many2one(related='move_id.expense_sheet_id.employee_id', string='Empleado')
    employee_partner_id = fields.Many2one(related='move_id.expense_employee_partner_id')
    invoice_residual = fields.Monetary(related='move_id.amount_residual', string='Saldo de la factura')

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario',
        compute='_compute_journal_id', store=True, readonly=False, precompute=True, required=True,
        check_company=True,
        domain="[('type', '=', 'general')]",
    )
    date = fields.Date(string='Fecha contable', required=True, default=fields.Date.context_today)
    line_ids = fields.One2many(
        comodel_name='hr.expense.settlement.wizard.line',
        inverse_name='wizard_id',
        string='Anticipos abiertos',
        compute='_compute_line_ids', store=True, readonly=False,
    )
    selected_advance_amount = fields.Monetary(
        string='Anticipos marcados',
        compute='_compute_amounts',
        help='Saldo disponible de los anticipos marcados, en la moneda de la factura.',
    )
    # Siempre se liquida el saldo completo: el comprobante ya lo pagó el empleado,
    # así que la factura nunca debe quedar con deuda al proveedor.
    amount = fields.Monetary(related='invoice_residual', string='Monto a liquidar')
    excess_amount = fields.Monetary(
        string='Saldo a reembolsar',
        compute='_compute_amounts',
        help='Parte de la factura que no cubren los anticipos marcados: queda como saldo a '
             'favor del empleado en la cuenta de entregas a rendir, para reembolsárselo.',
    )
    excess_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta del exceso',
        compute='_compute_excess_account_id', store=True, readonly=False,
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
    )

    @api.depends('move_id')
    def _compute_journal_id(self):
        for wizard in self:
            company = wizard.company_id
            journal = company.hr_expense_settlement_journal_id
            if wizard._get_chosen_advance_line()._l10n_pe_get_advance_kind() == 'petty_cash':
                journal = company.hr_expense_petty_cash_settlement_journal_id or journal
            wizard.journal_id = journal

    @api.depends('move_id')
    def _compute_line_ids(self):
        for wizard in self:
            advance_lines = wizard.move_id._get_expense_employee_advance_lines().filtered(
                lambda line: line.amount_residual > 0
            )
            chosen = wizard._get_chosen_advance_line()
            wizard.line_ids = [Command.clear()] + [
                Command.create({
                    'advance_line_id': line.id,
                    # Solo el anticipo elegido en el informe o, si no se eligió,
                    # los de la moneda de la factura: un gasto en dólares no
                    # consume un fondo en soles.
                    'selected': line == chosen if chosen else line.currency_id == wizard.currency_id,
                })
                for line in advance_lines
            ]

    @api.depends('amount', 'line_ids.selected', 'line_ids.available_amount')
    def _compute_amounts(self):
        for wizard in self:
            wizard.selected_advance_amount = wizard._get_selected_advance_amount()
            wizard.excess_amount = max(wizard.amount - wizard.selected_advance_amount, 0.0)

    @api.depends('line_ids.selected')
    def _compute_excess_account_id(self):
        for wizard in self:
            # El exceso queda en la cuenta de la moneda de la factura (p.ej. un
            # gasto en dólares, en la 1413001).
            same_currency_line = wizard.line_ids.filtered(
                lambda line: line.selected and line.advance_currency_id == wizard.currency_id
            )[:1]
            wizard.excess_account_id = same_currency_line.account_id or wizard._get_default_excess_account()

    def _get_default_excess_account(self):
        self.ensure_one()
        company = self.company_id
        if self._get_chosen_advance_line()._l10n_pe_get_advance_kind() == 'petty_cash':
            return company._get_hr_expense_petty_cash_account(self.currency_id)
        return company._get_hr_expense_advance_account(self.currency_id)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_chosen_advance_line(self):
        """Anticipo o fondo elegido en el informe de gastos (vacío: automático)."""
        self.ensure_one()
        chosen = self.move_id.expense_sheet_id.l10n_pe_advance_line_id
        return chosen if chosen.company_id == self.company_id else chosen.browse()

    def _get_selected_advance_amount(self):
        self.ensure_one()
        return sum(self.line_ids.filtered('selected').mapped('available_amount'))

    def _get_bill_rate(self):
        """Tipo de cambio de la factura (moneda de la compañía por unidad de la
        moneda de la factura), según su saldo pendiente."""
        self.ensure_one()
        payable_lines = self._get_open_payable_lines()
        amount_currency = sum(payable_lines.mapped('amount_residual_currency'))
        if self.currency_id.is_zero(amount_currency):
            return 0.0
        return sum(payable_lines.mapped('amount_residual')) / amount_currency

    def _convert(self, amount, from_currency, to_currency):
        self.ensure_one()
        company_currency = self.company_currency_id
        bill_rate = self.currency_id != company_currency and self._get_bill_rate()
        if bill_rate and {from_currency, to_currency} == {self.currency_id, company_currency}:
            converted = amount * bill_rate if from_currency == self.currency_id else amount / bill_rate
            return to_currency.round(converted)
        return from_currency._convert(amount, to_currency, self.company_id, self.date or fields.Date.context_today(self))

    def _allocate_advances(self):
        """Reparte el monto a aplicar entre los anticipos marcados, del más antiguo
        al más reciente. Devuelve {línea del wizard: monto en moneda de la factura}."""
        self.ensure_one()
        remaining = self.amount
        allocation = {}
        for line in self.line_ids.filtered('selected').sorted(lambda l: (l.date, l.advance_line_id.id)):
            applied = self.currency_id.round(max(min(remaining, line.available_amount), 0.0))
            allocation[line] = applied
            remaining -= applied
        return allocation

    def _get_open_payable_lines(self):
        self.ensure_one()
        return self.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable' and not line.reconciled
        )

    # -------------------------------------------------------------------------
    # Liquidación
    # -------------------------------------------------------------------------

    def _check_settlement(self):
        self.ensure_one()
        if not self.move_id.hr_expense_can_settle:
            raise UserError(_('La factura %s ya no tiene saldo pendiente por liquidar con anticipos.', self.move_id.name))
        if not self.currency_id.is_zero(self.excess_amount) and not self.excess_account_id:
            raise UserError(_('Indique la cuenta donde queda el exceso a reembolsar al empleado.'))

    def _prepare_settlement_lines(self):
        """Líneas del asiento de liquidación, cada una con la contrapartida que
        debe cancelar: las líneas por pagar de la factura, el anticipo que aplica
        o ninguna (el exceso queda abierto a favor del empleado).

        :return: lista de (apuntes a conciliar con la línea, valores de la línea)
        """
        self.ensure_one()
        company_currency = self.company_currency_id
        employee = self.employee_id.name
        credit_lines = []
        for line, applied in self._allocate_advances().items():
            if self.currency_id.is_zero(applied):
                continue
            advance = line.advance_line_id
            if self.currency_id.compare_amounts(applied, line.available_amount) == 0:
                amount_currency = advance.amount_residual_currency
            else:
                amount_currency = self._convert(applied, self.currency_id, advance.currency_id)
            credit_lines.append((advance, {
                'name': _('Rendición de %(employee)s: aplica anticipo %(advance)s', employee=employee, advance=advance.move_id.name),
                'account_id': advance.account_id.id,
                'partner_id': advance.partner_id.id,
                'currency_id': advance.currency_id.id,
                'amount_currency': -amount_currency,
                'balance': -self._get_company_balance(applied, amount_currency, advance.currency_id),
            }))
        if not self.currency_id.is_zero(self.excess_amount):
            # Respeta la moneda de la cuenta (p.ej. 1413001 solo admite USD).
            excess_currency = self.excess_account_id.currency_id or self.currency_id
            excess_amount_currency = self._convert(self.excess_amount, self.currency_id, excess_currency)
            credit_lines.append((self.env['account.move.line'], {
                'name': _('Rendición de %(employee)s: saldo a reembolsar', employee=employee),
                'account_id': self.excess_account_id.id,
                'partner_id': self.employee_partner_id.id,
                'currency_id': excess_currency.id,
                'amount_currency': -excess_amount_currency,
                'balance': -self._get_company_balance(self.excess_amount, excess_amount_currency, excess_currency),
            }))

        payable_lines = self._get_open_payable_lines()
        # Se cancela el saldo exacto de la cuenta por pagar: sin diferencia de
        # cambio en la factura (la liquidación usa su mismo tipo de cambio).
        debit_balance = -sum(payable_lines.mapped('amount_residual'))
        self._absorb_rounding(credit_lines, debit_balance)
        debit_line = (payable_lines, {
            'name': _('Rendición de %(employee)s: %(bill)s', employee=employee, bill=self.move_id.name),
            'account_id': payable_lines[:1].account_id.id,
            'partner_id': payable_lines[:1].partner_id.id,
            'currency_id': self.currency_id.id,
            'amount_currency': self.amount,
            'balance': debit_balance,
        })
        return [debit_line, *credit_lines]

    def _absorb_rounding(self, credit_lines, debit_balance):
        """Cuadra el asiento ajustando por redondeo una línea del haber: de
        preferencia una en moneda extranjera (solo su valor en la moneda de la
        compañía); si no, la última, en ambos importes."""
        company_currency = self.company_currency_id
        delta = company_currency.round(debit_balance + sum(vals['balance'] for _counterpart, vals in credit_lines))
        if company_currency.is_zero(delta):
            return
        foreign_vals = [vals for _counterpart, vals in credit_lines if vals['currency_id'] != company_currency.id]
        vals = (foreign_vals or [credit_lines[-1][1]])[-1]
        vals['balance'] -= delta
        if vals['currency_id'] == company_currency.id:
            vals['amount_currency'] -= delta

    def _prepare_settlement_move_vals(self, settlement_lines):
        self.ensure_one()
        return {
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': _('Rendición %(bill)s - %(employee)s', bill=self.move_id.name, employee=self.employee_id.name),
            'company_id': self.company_id.id,
            'hr_expense_settlement_bill_id': self.move_id.id,
            'line_ids': [Command.create(vals) for _counterpart, vals in settlement_lines],
        }

    def _get_company_balance(self, amount, amount_currency, currency):
        """Valor en moneda de la compañía de una línea: exacto si la línea o la
        factura ya están en moneda de la compañía, si no al cambio de la fecha."""
        if currency == self.company_currency_id:
            return amount_currency
        if self.currency_id == self.company_currency_id:
            return amount
        return self._convert(amount, self.currency_id, self.company_currency_id)

    def _reconcile_settlement(self, settlement, settlement_lines):
        """Concilia cada línea del asiento con su propia contrapartida. Dejarlo a
        la conciliación por cuenta cruzaba el anticipo con la línea del exceso."""
        self.ensure_one()
        # Las líneas se crean en el orden de settlement_lines.
        for move_line, (counterpart, _vals) in zip(settlement.line_ids.sorted('id'), settlement_lines):
            if counterpart:
                (counterpart + move_line).reconcile()

    def _log_settlement(self, settlement):
        self.ensure_one()
        body = Markup(_('Liquidación de rendición registrada: %(move)s por %(amount)s.')) % {
            'move': settlement._get_html_link(),
            'amount': self.currency_id.format(self.amount),
        }
        self.move_id.message_post(body=body)
        if self.move_id.expense_sheet_id:
            self.move_id.expense_sheet_id.message_post(body=Markup('%s<br/>%s') % (self.move_id._get_html_link(), body))

    def action_confirm(self):
        self.ensure_one()
        self._check_settlement()
        settlement_lines = self._prepare_settlement_lines()
        settlement = self.env['account.move'].create(self._prepare_settlement_move_vals(settlement_lines))
        settlement.action_post()
        if settlement.state != 'posted':
            raise UserError(_(
                'No se pudo publicar el asiento de liquidación en el diario "%s". Verifique que el diario '
                'no requiera aprobación.', self.journal_id.name,
            ))
        self._reconcile_settlement(settlement, settlement_lines)
        self._log_settlement(settlement)
        return {'type': 'ir.actions.act_window_close'}


class HrExpenseSettlementWizardLine(models.TransientModel):
    _name = 'hr.expense.settlement.wizard.line'
    _description = 'Anticipo abierto a aplicar en la rendición'
    _order = 'date, id'

    wizard_id = fields.Many2one('hr.expense.settlement.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    selected = fields.Boolean(string='Aplicar', default=True)
    advance_line_id = fields.Many2one('account.move.line', string='Apunte del anticipo', required=True, readonly=True)
    advance_move_id = fields.Many2one(related='advance_line_id.move_id', string='Anticipo')
    date = fields.Date(related='advance_line_id.date', string='Fecha')
    account_id = fields.Many2one(related='advance_line_id.account_id', string='Cuenta')
    name = fields.Char(related='advance_line_id.name', string='Etiqueta')
    advance_currency_id = fields.Many2one(related='advance_line_id.currency_id', string='Moneda del anticipo')
    amount_residual_currency = fields.Monetary(
        related='advance_line_id.amount_residual_currency',
        currency_field='advance_currency_id',
        string='Saldo del anticipo',
    )
    available_amount = fields.Monetary(
        string='Disponible',
        compute='_compute_available_amount',
        help='Saldo del anticipo en la moneda de la factura, al tipo de cambio de la fecha contable.',
    )
    applied_amount = fields.Monetary(string='A aplicar', compute='_compute_applied_amount')

    @api.depends('advance_line_id', 'wizard_id.date')
    def _compute_available_amount(self):
        for line in self:
            line.available_amount = line.wizard_id._convert(
                line.amount_residual_currency, line.advance_currency_id, line.currency_id,
            )

    @api.depends('selected', 'available_amount', 'wizard_id.amount')
    def _compute_applied_amount(self):
        allocations = {}
        for wizard in self.wizard_id:
            allocations.update(wizard._allocate_advances())
        for line in self:
            line.applied_amount = allocations.get(line, 0.0)
