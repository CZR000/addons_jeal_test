from markupsafe import Markup

from odoo import api, fields, models, _, Command
from odoo.exceptions import RedirectWarning, UserError
from odoo.tools import groupby
from odoo.tools.misc import clean_context


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    l10n_pe_has_vendor_receipts = fields.Boolean(
        string='Tiene comprobantes de proveedor',
        compute='_compute_l10n_pe_has_vendor_receipts',
        help='El informe genera facturas a nombre de los proveedores: se liquidan desde cada '
             'factura con "Conciliar con Anticipo", no pagando el informe.',
    )

    l10n_pe_available_advance_line_ids = fields.Many2many(
        comodel_name='account.move.line',
        compute='_compute_l10n_pe_available_advance_line_ids',
    )
    l10n_pe_advance_line_id = fields.Many2one(
        comodel_name='account.move.line',
        string='Anticipo / fondo',
        domain="[('id', 'in', l10n_pe_available_advance_line_ids)]",
        copy=False,
        tracking=True,
        help='Anticipo o fondo de caja chica que rinde este informe. Se ofrecen los de la moneda '
             'de sus comprobantes. Vacío: se aplican los anticipos en la moneda de cada '
             'comprobante, del más antiguo al más reciente.',
    )
    l10n_pe_advance_currency_warning = fields.Char(
        string='Aviso de moneda del anticipo',
        compute='_compute_l10n_pe_advance_currency_warning',
    )
    l10n_pe_has_refund_hints = fields.Boolean(compute='_compute_l10n_pe_has_refund_hints')
    l10n_pe_is_petty_cash = fields.Boolean(compute='_compute_l10n_pe_is_petty_cash')
    l10n_pe_replenish_request_ids = fields.One2many(
        comodel_name='approval.request',
        inverse_name='l10n_pe_expense_sheet_id',
        string='Reposiciones del fondo',
    )
    l10n_pe_replenish_request_label = fields.Char(
        string='Reposición',
        compute='_compute_l10n_pe_replenish_request_label',
        help='Número y estado de la solicitud de reposición del fondo creada desde este informe.',
    )
    l10n_pe_petty_cash_balance = fields.Monetary(
        string='Saldo total del fondo',
        currency_field='company_currency_id',
        compute='_compute_l10n_pe_petty_cash_balance',
        help='Saldo de caja chica del empleado sumando todas sus líneas (desembolsos y reposiciones '
             'menos lo rendido).',
    )
    l10n_pe_balance_to_settle = fields.Monetary(
        string='Saldo por liquidar',
        currency_field='company_currency_id',
        compute='_compute_l10n_pe_balance_to_settle',
        help='Saldo pendiente en la cuenta 14 de los anticipos que rinde este informe. Positivo: '
             'el empleado debe devolverlo; negativo: hay que reembolsárselo.',
    )

    @api.depends('employee_id', 'company_id', 'expense_line_ids.currency_id')
    def _compute_l10n_pe_available_advance_line_ids(self):
        for sheet in self:
            # Solo los anticipos de la moneda de los comprobantes: un informe en
            # soles no rinde una entrega en dólares (sin comprobantes aún, todos).
            lines = sheet._l10n_pe_get_open_advance_lines()
            currencies = sheet.expense_line_ids.currency_id
            sheet.l10n_pe_available_advance_line_ids = (
                lines.filtered(lambda line: line.currency_id in currencies) if currencies else lines
            )

    @api.depends('l10n_pe_advance_line_id', 'expense_line_ids.currency_id')
    def _compute_l10n_pe_advance_currency_warning(self):
        for sheet in self:
            advance_currency = sheet.l10n_pe_advance_line_id.currency_id
            other_currencies = sheet.expense_line_ids.currency_id - advance_currency
            sheet.l10n_pe_advance_currency_warning = advance_currency and other_currencies and _(
                'El anticipo elegido está en %(advance)s y hay comprobantes en %(others)s: se aplicará '
                'convirtiendo al tipo de cambio de cada factura. Verifique que sea el anticipo correcto.',
                advance=advance_currency.name, others=', '.join(other_currencies.mapped('name')),
            ) or False

    @api.depends('expense_line_ids.l10n_pe_looks_like_refund')
    def _compute_l10n_pe_has_refund_hints(self):
        for sheet in self:
            sheet.l10n_pe_has_refund_hints = any(sheet.expense_line_ids.mapped('l10n_pe_looks_like_refund'))

    @api.depends('l10n_pe_advance_line_id')
    def _compute_l10n_pe_is_petty_cash(self):
        for sheet in self:
            sheet.l10n_pe_is_petty_cash = sheet.l10n_pe_advance_line_id._l10n_pe_get_advance_kind() == 'petty_cash'

    @api.depends('l10n_pe_replenish_request_ids.request_status')
    def _compute_l10n_pe_replenish_request_label(self):
        statuses = dict(self.env['approval.request']._fields['request_status']._description_selection(self.env))
        for sheet in self:
            request = sheet.l10n_pe_replenish_request_ids.sorted('id')[-1:]
            sheet.l10n_pe_replenish_request_label = request and f"{request.name} – {statuses.get(request.request_status)}"

    @api.depends('l10n_pe_is_petty_cash', 'state', 'account_move_ids.payment_state')
    def _compute_l10n_pe_petty_cash_balance(self):
        for sheet in self:
            sheet.l10n_pe_petty_cash_balance = (
                sheet.l10n_pe_is_petty_cash and sheet.employee_id._l10n_pe_get_petty_cash_balance(sheet.company_id)
            )

    @api.depends('state', 'account_move_ids.payment_state', 'expense_line_ids.l10n_pe_refund_payment_id')
    def _compute_l10n_pe_balance_to_settle(self):
        for sheet in self:
            sheet.l10n_pe_balance_to_settle = sum(sheet._l10n_pe_get_balance_lines().mapped('amount_residual'))

    @api.depends('expense_line_ids.vendor_id', 'expense_line_ids.payment_mode')
    def _compute_l10n_pe_has_vendor_receipts(self):
        for sheet in self:
            sheet.l10n_pe_has_vendor_receipts = any(
                expense._l10n_pe_is_vendor_receipt() for expense in sheet.expense_line_ids
            )

    # -------------------------------------------------------------------------
    # Estado de pago: con comprobantes de proveedor, un informe reembolsable
    # tiene varias facturas (la nativa asume una sola).
    # -------------------------------------------------------------------------

    @api.depends('account_move_ids.payment_state', 'account_move_ids.amount_residual')
    def _compute_from_account_move_ids(self):
        multi_bill_sheets = self.filtered(
            lambda sheet: sheet.payment_mode == 'own_account' and len(sheet.account_move_ids) > 1
        )
        super(HrExpenseSheet, self - multi_bill_sheets)._compute_from_account_move_ids()
        for sheet in multi_bill_sheets:
            posted_moves = sheet.account_move_ids.filtered(lambda move: move.state == 'posted')
            # Las facturas pueden estar en moneda extranjera: el saldo del
            # informe se expresa en la moneda de la compañía.
            sheet.amount_residual = sum(abs(amount) for amount in posted_moves.mapped('amount_residual_signed'))
            sheet.payment_state = self._l10n_pe_merge_payment_states(set(posted_moves.mapped('payment_state')))

    @api.depends('expense_line_ids.l10n_pe_refund_payment_id.state')
    def _compute_state(self):
        super()._compute_state()
        # Un informe sin facturas (p.ej. que solo devuelve el sobrante) queda
        # terminado cuando se registra lo de cada línea (el cobro de la devolución).
        for sheet in self.filtered(lambda sheet: sheet.state == 'approve' and not sheet.account_move_ids):
            expenses = sheet.expense_line_ids
            if expenses and all(expense._l10n_pe_is_done_without_bill() for expense in expenses):
                sheet.state = 'done'

    @api.model
    def _l10n_pe_merge_payment_states(self, states):
        if not states:
            return 'not_paid'
        if len(states) == 1:
            return states.pop()
        if states <= {'paid', 'reversed'}:
            return 'paid'
        if states <= {'paid', 'in_payment', 'reversed'}:
            return 'in_payment'
        if states & {'paid', 'in_payment', 'partial'}:
            return 'partial'
        return 'not_paid'

    # -------------------------------------------------------------------------
    # Una factura de proveedor por comprobante
    # -------------------------------------------------------------------------

    def _do_submit(self):
        # Los datos del comprobante se exigen al enviar el informe, no recién al
        # contabilizarlo cuando ya está aprobado.
        self.filtered(lambda sheet: sheet.payment_mode == 'own_account').expense_line_ids._l10n_pe_check_receipt_data()
        super()._do_submit()

    def _check_can_create_move(self):
        super()._check_can_create_move()
        self._l10n_pe_check_advance_refunds()

    def _validate_analytic_distribution(self):
        # Una devolución no es un gasto: no exige centro de costos.
        for sheet in self:
            for line in sheet._l10n_pe_invoiced_expenses():
                line._validate_distribution(
                    account=line.account_id.id, product=line.product_id.id,
                    business_domain='expense', company_id=line.company_id.id,
                )

    def action_sheet_move_post(self):
        # El botón se oculta en pantalla, pero la acción también se puede llamar
        # por importación, acción masiva o RPC.
        not_approved = self.filtered(lambda sheet: sheet.state != 'approve')
        if not_approved:
            raise UserError(_(
                'El informe debe estar aprobado para contabilizarlo: %s',
                ', '.join(not_approved.mapped('name')),
            ))
        res = super().action_sheet_move_post()
        self._l10n_pe_post_advance_refunds()
        return res

    def _do_reverse_moves(self):
        """Restablecer un informe contabilizado. La reversión nativa crea una nota de
        crédito con el tipo de documento de la factura (l10n_latam la rechaza: "No
        puedes utilizar el tipo de documento invoice en una factura de reembolso") y
        dejaría en el Registro de Compras una nota de crédito que el proveedor no
        emitió. Con el periodo abierto, las facturas del informe y sus liquidaciones se
        anulan: el anticipo o el fondo recupera su saldo. En un periodo cerrado se
        avisa (la corrección es con una nota de crédito del proveedor)."""
        moves = self.sudo().account_move_ids.filtered(lambda move: move.state == 'posted')
        settlements = moves.hr_expense_settlement_move_ids.filtered(lambda move: move.state == 'posted')
        locked = (moves | settlements).filtered(lambda move: not move._can_be_unlinked())
        locked_documents = locked.filtered('l10n_latam_document_type_id')
        if locked_documents:
            raise UserError(_(
                'No se puede restablecer el informe: las siguientes facturas están en un periodo cerrado y no se '
                'pueden anular. Registre la nota de crédito del proveedor o abra el periodo:\n%s',
                '\n'.join(f'- {move.display_name} ({move.date:%d/%m/%Y})' for move in locked_documents),
            ))
        to_cancel = (moves | settlements) - locked
        if to_cancel:
            to_cancel.with_context(clean_context(self.env.context)).button_draft()
            to_cancel.with_context(clean_context(self.env.context)).button_cancel()
        locked_settlements = settlements & locked
        if locked_settlements:
            today = fields.Date.context_today(self)
            locked_settlements._reverse_moves([{'date': today} for _move in locked_settlements], cancel=True)
        return super()._do_reverse_moves()

    def action_reset_expense_sheets(self):
        refund_payments = self.expense_line_ids.l10n_pe_refund_payment_id
        res = super().action_reset_expense_sheets()
        if refund_payments:
            refund_payments.filtered(lambda payment: payment.state != 'draft').action_draft()
            refund_payments.action_cancel()
            self.expense_line_ids.l10n_pe_refund_payment_id = False
        return res

    def _l10n_pe_bill_expenses(self):
        """Gastos rendidos (todo menos las devoluciones): lo que consume el anticipo
        o el fondo."""
        return self.expense_line_ids.filtered(lambda expense: not expense.l10n_pe_is_advance_refund)

    def _l10n_pe_invoiced_expenses(self):
        """Gastos que generan factura en la empresa del informe."""
        return self._l10n_pe_bill_expenses()

    def _do_create_moves(self):
        # Un informe sin gastos que facturar (p.ej. que solo devuelve el sobrante)
        # no tiene facturas que crear.
        refund_only_sheets = self.filtered(lambda sheet: not sheet._l10n_pe_invoiced_expenses())
        self -= refund_only_sheets
        # La cadena nativa (y sus extensiones, p.ej. sale_expense) crea la primera
        # factura de cada informe vía _prepare_bills_vals; aquí solo se agregan las
        # facturas de los demás comprobantes.
        self.filtered(lambda sheet: sheet.payment_mode == 'own_account').expense_line_ids._l10n_pe_check_receipt_data()
        receipt_sheets = self.filtered(lambda sheet: sheet.l10n_pe_has_vendor_receipts)
        moves_sudo = super()._do_create_moves()
        extra_vals_list = [vals for sheet in receipt_sheets for vals in sheet._l10n_pe_prepare_bills_vals_list()[1:]]
        if extra_vals_list:
            extra_moves_sudo = self.env['account.move'].with_context(clean_context(self.env.context)).sudo().create(extra_vals_list)
            for move_sudo in extra_moves_sudo:
                move_sudo._message_set_main_attachment_id(move_sudo.attachment_ids, force=True, filter_xml=False)
            moves_sudo |= extra_moves_sudo.sudo(self.env.su)
        return moves_sudo

    def _prepare_bills_vals(self):
        return self._l10n_pe_prepare_bills_vals_list()[0]

    def _l10n_pe_prepare_bills_vals_list(self):
        """Una factura por comprobante de proveedor, más la factura nativa (a nombre
        del empleado) para los gastos sin proveedor."""
        self.ensure_one()
        # Se parte de los valores nativos para conservar lo que otros módulos
        # agreguen a la factura del informe.
        base_vals = super()._prepare_bills_vals()
        bill_expenses = self._l10n_pe_invoiced_expenses()
        receipt_expenses = bill_expenses.filtered(lambda expense: expense._l10n_pe_is_vendor_receipt())
        employee_expenses = bill_expenses - receipt_expenses

        vals_list = []
        if employee_expenses:
            # Gastos sin comprobante de proveedor (p.ej. movilidad sin sustento): no
            # van al Registro de Compras (se exige el proveedor para ir), así que la
            # factura a nombre del empleado va al diario fuera del Registro de Compras.
            vals_list.append({
                **base_vals,
                **self._l10n_pe_prepare_expenses_bill_vals(employee_expenses),
                'journal_id': self._l10n_pe_get_receipt_journal(employee_expenses[0]).id,
            })
        for _key, expenses in groupby(receipt_expenses, key=lambda expense: expense._l10n_pe_get_receipt_key()):
            vals_list.append(self._l10n_pe_prepare_receipt_bill_vals(
                base_vals, self.env['hr.expense'].union(*expenses),
            ))
        return vals_list

    @api.model
    def _l10n_pe_prepare_expenses_bill_vals(self, expenses):
        return {
            'line_ids': [Command.create(expense._prepare_move_lines_vals()) for expense in expenses],
            'attachment_ids': [
                Command.create(attachment.copy_data({'res_model': 'account.move', 'res_id': False, 'raw': attachment.raw})[0])
                for attachment in expenses.attachment_ids
            ],
        }

    def _l10n_pe_prepare_receipt_bill_vals(self, base_vals, expenses):
        self.ensure_one()
        receipt = expenses[0]
        journal = self._l10n_pe_get_receipt_journal(receipt)
        vals = {
            **{key: value for key, value in base_vals.items() if key not in ('commercial_partner_id', 'partner_bank_id')},
            **self._l10n_pe_prepare_expenses_bill_vals(expenses),
            'journal_id': journal.id,
            'partner_id': receipt.vendor_id.id,
            'currency_id': receipt.currency_id.id,
            'ref': receipt.l10n_pe_document_reference or base_vals['ref'],
            'l10n_latam_document_type_id': receipt.l10n_pe_document_type_id.id,
            # Fecha de emisión del comprobante; la contable es la del informe.
            'invoice_date': receipt.date or self.accounting_date,
            'date': self.accounting_date,
        }
        if journal.l10n_latam_use_documents and receipt.l10n_pe_document_reference:
            vals['l10n_latam_document_number'] = receipt.l10n_pe_document_reference
        if receipt.currency_id != receipt.company_currency_id and receipt.currency_rate:
            # Mismo tipo de cambio que se aprobó en el gasto.
            vals['invoice_currency_rate'] = 1 / receipt.currency_rate
        return vals

    def _l10n_pe_get_receipt_journal(self, expense):
        self.ensure_one()
        if expense.l10n_pe_in_purchase_register:
            return self.journal_id
        journal = self.company_id.hr_expense_non_register_journal_id
        if not journal:
            raise RedirectWarning(
                _('Configure el "Diario de comprobantes fuera del Registro de Compras" de la compañía '
                  '%(company)s para registrar el gasto "%(expense)s".',
                  company=self.company_id.name, expense=expense.name),
                self.env.ref('hr_expense.action_hr_expense_configuration').id,
                _('Ir a Ajustes'),
            )
        return journal

    # -------------------------------------------------------------------------
    # Anticipos que rinde el informe
    # -------------------------------------------------------------------------

    def _l10n_pe_get_open_advance_lines(self, currency=None):
        """Anticipos y fondos abiertos del empleado (saldo deudor en la 14), del
        más antiguo al más reciente."""
        self.ensure_one()
        partner = self.employee_id.sudo().work_contact_id
        if not partner:
            return self.env['account.move.line']
        domain = [
            ('company_id', '=', self.company_id.id),
            ('partner_id', '=', partner.id),
            ('account_id', 'in', self.company_id._get_hr_expense_employee_accounts().ids),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '>', 0),
        ]
        if currency:
            domain.append(('currency_id', '=', currency.id))
        return self.env['account.move.line'].search(domain, order='date, id')

    def _l10n_pe_get_balance_lines(self):
        """Apuntes abiertos de la 14 que dejó la rendición: los anticipos que
        aplicaron sus liquidaciones y devoluciones (o el elegido) y los saldos a
        reembolsar al empleado. Un fondo de caja chica no se devuelve, se repone:
        su saldo no es un saldo por liquidar."""
        self.ensure_one()
        if self.state not in ('post', 'done'):
            return self.env['account.move.line']
        accounts = self.company_id._get_hr_expense_employee_accounts()
        own_lines = self._l10n_pe_get_rendition_moves().line_ids.filtered(lambda line: line.account_id in accounts)
        applied_advances = (
            own_lines.matched_debit_ids.debit_move_id | own_lines.matched_credit_ids.credit_move_id
        ).filtered(lambda line: line.account_id in accounts)
        lines = own_lines | applied_advances | self.l10n_pe_advance_line_id
        return lines.filtered(lambda line: (
            not line.reconciled
            and line.parent_state == 'posted'
            and line._l10n_pe_get_advance_kind() != 'petty_cash'
        ))

    def _l10n_pe_get_rendition_moves(self):
        """Asientos publicados de la rendición que mueven la cuenta 14 del empleado:
        liquidaciones de las facturas y cobros de las devoluciones."""
        self.ensure_one()
        settlements = self.account_move_ids.hr_expense_settlement_move_ids
        refund_moves = self.expense_line_ids.l10n_pe_refund_payment_id.move_id
        return (settlements | refund_moves).filtered(lambda move: move.state == 'posted')

    def action_l10n_pe_settle_balance(self):
        """Abre el pago (saldo a favor del empleado) o el cobro (a favor de la
        empresa) del saldo de la rendición; al confirmarlo concilia la 14."""
        self.ensure_one()
        lines = self._l10n_pe_get_balance_lines()
        if not lines:
            raise UserError(_('El informe %s no tiene saldo por liquidar.', self.name))
        action = lines.action_register_payment()
        payment_type = 'inbound' if sum(lines.mapped('amount_residual')) > 0 else 'outbound'
        action['context'] = {**action.get('context', {}), **self._l10n_pe_get_settle_balance_context(payment_type)}
        return action

    def _l10n_pe_get_settle_balance_context(self, payment_type):
        """Contexto del asistente de pago de "Liquidar saldo": cobro (inbound) del
        sobrante o pago (outbound) del saldo a favor del empleado."""
        return {}

    # -------------------------------------------------------------------------
    # Devolución del sobrante
    # -------------------------------------------------------------------------

    def _l10n_pe_get_refund_advance_lines(self, refund):
        """Anticipos a los que se aplica una devolución: el elegido en el
        informe o los abiertos de su moneda (de una misma cuenta)."""
        self.ensure_one()
        if self.l10n_pe_advance_line_id:
            return self.l10n_pe_advance_line_id.filtered(lambda line: not line.reconciled)
        lines = self._l10n_pe_get_open_advance_lines(refund.currency_id)
        return lines.filtered(lambda line: line.account_id == lines[:1].account_id)

    def _l10n_pe_check_advance_refunds(self):
        for sheet in self:
            for refund in sheet.expense_line_ids.filtered(
                lambda expense: expense.l10n_pe_is_advance_refund and not expense.l10n_pe_refund_payment_id
            ):
                if not refund.l10n_pe_refund_journal_id or not refund.date:
                    raise UserError(_(
                        'Indique el banco o la caja y la fecha de la devolución "%s".', refund.name,
                    ))
                advances = sheet._l10n_pe_get_refund_advance_lines(refund)
                pending = sum(advances.mapped('amount_residual_currency'))
                if refund.currency_id.compare_amounts(refund.total_amount_currency, pending) > 0:
                    raise UserError(_(
                        'La devolución "%(refund)s" por %(amount)s supera el saldo pendiente del anticipo '
                        '(%(pending)s).',
                        refund=refund.name,
                        amount=refund.currency_id.format(refund.total_amount_currency),
                        pending=refund.currency_id.format(pending),
                    ))

    def _l10n_pe_post_advance_refunds(self):
        """Cada devolución genera un cobro en el banco o caja elegidos (Debe banco /
        Haber 14 empleado) conciliado con el anticipo. Se ejecuta después de
        publicar las facturas, que ya consumieron su parte del anticipo."""
        self._l10n_pe_check_advance_refunds()
        for sheet in self:
            partner = sheet.employee_id.sudo().work_contact_id
            for refund in sheet.expense_line_ids.filtered(
                lambda expense: expense.l10n_pe_is_advance_refund and not expense.l10n_pe_refund_payment_id
            ):
                advances = sheet._l10n_pe_get_refund_advance_lines(refund)
                payment = self.env['account.payment'].create(
                    sheet._l10n_pe_prepare_refund_payment_vals(refund, partner, advances)
                )
                payment._l10n_pe_ensure_journal_entry()
                payment.action_post()
                payment_line = payment.move_id.line_ids.filtered(
                    lambda line: line.account_id == advances[:1].account_id
                )
                (payment_line + advances).reconcile()
                refund.l10n_pe_refund_payment_id = payment
                sheet.message_post(body=Markup(_('Devolución registrada: %s')) % payment._get_html_link())

    def _l10n_pe_prepare_refund_payment_vals(self, refund, partner, advances):
        self.ensure_one()
        return {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': refund.total_amount_currency,
            'currency_id': refund.currency_id.id,
            'date': refund.date,
            'journal_id': refund.l10n_pe_refund_journal_id.id,
            'destination_account_id': advances[:1].account_id.id,
            'memo': _('Devolución de entrega a rendir: %(sheet)s', sheet=self.name),
        }

    # -------------------------------------------------------------------------
    # Fondo de caja chica
    # -------------------------------------------------------------------------

    def action_l10n_pe_replenish_fund(self):
        """Solicitud de reposición del fondo de caja chica por el total rendido."""
        self.ensure_one()
        fund = self.l10n_pe_advance_line_id
        fund_request = fund.move_id.origin_payment_id.approval_request_id
        if not self.l10n_pe_is_petty_cash or not fund_request:
            raise UserError(_('El informe %s no rinde un fondo de caja chica.', self.name))
        expenses = self._l10n_pe_bill_expenses()
        currency = fund.currency_id
        amount = sum(
            expense.total_amount_currency if expense.currency_id == currency
            else self.company_currency_id._convert(expense.total_amount, currency, self.company_id, expense.date)
            for expense in expenses
        )
        request = self.env['approval.request'].create({
            'category_id': fund_request.category_id.id,
            'request_owner_id': (self.employee_id.user_id or self.env.user).id,
            'l10n_pe_employee_id': self.employee_id.id,
            'l10n_pe_currency_id': currency.id,
            'amount': currency.round(amount),
            'reason': _('Reposición del fondo de caja chica por el informe %s.', self.name),
            'l10n_pe_expense_sheet_id': self.id,
        })
        request._l10n_pe_set_category_approvers()
        return request._get_records_action()

    def action_l10n_pe_open_replenish_request(self):
        self.ensure_one()
        return self.l10n_pe_replenish_request_ids.sorted('id')[-1:]._get_records_action()
