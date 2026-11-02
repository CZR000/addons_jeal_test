from markupsafe import Markup

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError
from odoo.tools import groupby
from odoo.tools.misc import clean_context


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    l10n_pe_ic_move_ids = fields.Many2many(
        comodel_name='account.move',
        string='Asientos intercompany',
        compute='_compute_l10n_pe_ic_move_ids',
    )
    l10n_pe_ic_move_count = fields.Integer(compute='_compute_l10n_pe_ic_move_ids')
    l10n_pe_ic_vat_warning = fields.Char(compute='_compute_l10n_pe_ic_vat_warning')

    @api.depends('expense_line_ids.l10n_pe_ic_move_id')
    def _compute_l10n_pe_ic_move_ids(self):
        for sheet in self:
            sheet.l10n_pe_ic_move_ids = sheet.expense_line_ids.l10n_pe_ic_move_id
            sheet.l10n_pe_ic_move_count = len(sheet.l10n_pe_ic_move_ids)

    @api.depends('expense_line_ids.l10n_pe_ic_vat_mismatch')
    def _compute_l10n_pe_ic_vat_warning(self):
        for sheet in self:
            expenses = sheet.expense_line_ids.filtered('l10n_pe_ic_vat_mismatch')
            sheet.l10n_pe_ic_vat_warning = _(
                'RUC del adquiriente distinto al de la empresa que asume el gasto: %s. Verifique los comprobantes '
                'antes de enviar el informe.', ', '.join(
                    f'{expense.name} ({expense.l10n_pe_ic_customer_vat or "-"} / '
                    f'{expense.l10n_pe_charged_partner_id.name} {expense.l10n_pe_charged_partner_id.vat or ""})'
                    for expense in expenses)) if expenses else False

    @api.depends('expense_line_ids.l10n_pe_ic_move_id.state')
    def _compute_state(self):
        super()._compute_state()

    def _l10n_pe_invoiced_expenses(self):
        # Los comprobantes de otra empresa no se facturan aquí.
        return super()._l10n_pe_invoiced_expenses().filtered(lambda expense: not expense.l10n_pe_is_intercompany)

    def _l10n_pe_get_rendition_moves(self):
        return super()._l10n_pe_get_rendition_moves() | self.expense_line_ids.l10n_pe_ic_move_id.filtered(
            lambda move: move.state == 'posted'
        )

    def _l10n_pe_post_advance_refunds(self):
        # Primero lo de las otras empresas (consume el anticipo como las facturas),
        # después el cobro del sobrante.
        self._l10n_pe_post_intercompany_expenses()
        return super()._l10n_pe_post_advance_refunds()

    def action_reset_expense_sheets(self):
        self._l10n_pe_undo_intercompany_expenses()
        return super().action_reset_expense_sheets()

    def action_l10n_pe_open_ic_moves(self):
        self.ensure_one()
        return self.l10n_pe_ic_move_ids._get_records_action(name=_('Asientos intercompany'))

    # -------------------------------------------------------------------------
    # Contabilizar
    # -------------------------------------------------------------------------

    def _l10n_pe_post_intercompany_expenses(self):
        """Por cada comprobante de otra empresa: el asiento de la cuenta por cobrar
        intercompany aquí y la factura en borrador allá."""
        for sheet in self:
            expenses = sheet.expense_line_ids.filtered(
                lambda expense: expense.l10n_pe_is_intercompany and not expense.l10n_pe_ic_move_id
            )
            if not expenses:
                continue
            expenses._l10n_pe_check_intercompany()
            for _key, receipt in groupby(expenses, key=lambda expense: (
                    expense.l10n_pe_charged_partner_id.id, expense._l10n_pe_get_receipt_key())):
                receipt = self.env['hr.expense'].union(*receipt)
                move = sheet._l10n_pe_create_ic_move(receipt)
                bill = sheet._l10n_pe_create_ic_bill(receipt, move)
                company = receipt[0]._l10n_pe_get_charged_company()
                receipt.write({
                    'l10n_pe_ic_move_id': move.id,
                    'l10n_pe_ic_bill_ref': f'{company.name}: {bill.display_name}',
                    'l10n_pe_ic_bill_res_id': bill.id,
                })
                sheet.message_post(body=Markup(_(
                    'Comprobante %(receipt)s a cargo de %(company)s: %(move)s. Se creó la factura en borrador '
                    '%(bill)s en %(company)s para que la revise su contadora.')) % {
                    'receipt': receipt[0].l10n_pe_document_reference, 'company': company.name,
                    'move': move._get_html_link(), 'bill': bill.display_name,
                })

    def _l10n_pe_get_ic_advance_lines(self, currency):
        """Anticipo o fondo que consume un comprobante de otra empresa: el elegido en
        el informe o los abiertos de su moneda (de una misma cuenta)."""
        self.ensure_one()
        if self.l10n_pe_advance_line_id:
            return self.l10n_pe_advance_line_id.filtered(lambda line: not line.reconciled)
        lines = self._l10n_pe_get_open_advance_lines(currency)
        return lines.filtered(lambda line: line.account_id == lines[:1].account_id)

    def _l10n_pe_create_ic_move(self, expenses):
        """Debe cuenta por cobrar intercompany (a nombre de la otra empresa) / Haber
        cuenta 14 del empleado, conciliada con el anticipo o el fondo."""
        self.ensure_one()
        company = self.company_id
        first = expenses[0]
        currency = first.currency_id
        charged = first._l10n_pe_get_charged_company()
        advances = self._l10n_pe_get_ic_advance_lines(currency)
        employee_account = advances[:1].account_id or company._get_hr_expense_advance_account(currency)
        if not employee_account:
            raise UserError(_('Configure las "Cuentas de entregas a rendir" de la compañía %s.', company.name))
        journal = (
            (self.l10n_pe_is_petty_cash and company.hr_expense_petty_cash_settlement_journal_id)
            or company.hr_expense_settlement_journal_id
        )
        if not journal:
            raise UserError(_('Configure el "Diario de liquidación" de la rendición de gastos de %s.', company.name))
        amount_currency = sum(expenses.mapped('total_amount_currency'))
        balance = sum(expenses.mapped('total_amount'))
        label = _('%(receipt)s %(vendor)s · a cargo de %(company)s',
                  receipt=first.l10n_pe_document_reference, vendor=first.vendor_id.name, company=charged.name)
        common = {'name': label, 'currency_id': currency.id}
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'company_id': company.id,
            'journal_id': journal.id,
            'date': self.accounting_date or fields.Date.context_today(self),
            # Misma referencia en las dos empresas: el número del informe.
            'ref': self.name,
            'line_ids': [
                Command.create({
                    **common,
                    'account_id': company._get_hr_expense_ic_account('receivable', currency).id,
                    'partner_id': charged.partner_id.id,
                    'amount_currency': amount_currency,
                    'balance': balance,
                }),
                Command.create({
                    **common,
                    'account_id': employee_account.id,
                    'partner_id': self.employee_id.sudo().work_contact_id.id,
                    'amount_currency': -amount_currency,
                    'balance': -balance,
                }),
            ],
        })
        move.action_post()
        credit = move.line_ids.filtered(lambda line: line.account_id == employee_account)
        advances = advances.filtered(lambda line: line.account_id == employee_account)
        if advances:
            (credit + advances).reconcile()
        return move

    @api.model
    def _l10n_pe_map_ic_taxes(self, taxes, company):
        """Impuestos de la otra empresa con el mismo nombre (p.ej. "18%-C")."""
        mapped = self.env['account.tax'].sudo()
        missing = []
        for tax in taxes:
            match = self.env['account.tax'].sudo().search([
                *self.env['account.tax']._check_company_domain(company),
                ('name', '=', tax.name),
                ('type_tax_use', '=', tax.type_tax_use),
            ], limit=1)
            if match:
                mapped |= match
            else:
                missing.append(tax.name)
        return mapped, missing

    @api.model
    def _l10n_pe_get_ic_line_taxes(self, expense, product, company):
        """Impuestos de compra del producto en la otra empresa si equivalen a los del
        comprobante (mismas tasas); si no, los del comprobante por nombre."""
        def signature(taxes):
            return sorted((tax.amount_type, tax.amount, tax.price_include) for tax in taxes)

        product_taxes = product.sudo().with_company(company).supplier_taxes_id.filtered(
            lambda tax: tax.company_id.root_id == company.root_id
        )
        if product and signature(product_taxes) == signature(expense.tax_ids):
            return product_taxes, []
        taxes, missing = self._l10n_pe_map_ic_taxes(expense.tax_ids, company)
        return (self.env['account.tax'] if missing else taxes), missing

    @api.model
    def _l10n_pe_get_ic_analytic_distribution(self, expense, company):
        """Analítica del gasto que también es de la otra empresa (cuentas compartidas o
        suyas). Si no hay, la toma Odoo de los modelos de distribución analítica."""
        distribution = {}
        for key, percentage in (expense.analytic_distribution or {}).items():
            accounts = self.env['account.analytic.account'].sudo().browse(int(i) for i in key.split(',')).exists()
            if accounts and len(accounts) == len(key.split(',')) and all(
                    account.company_id in (company, self.env['res.company']) for account in accounts):
                distribution[key] = percentage
        return distribution

    def _l10n_pe_create_ic_bill(self, expenses, ic_move):
        """Factura de proveedor en BORRADOR en la empresa que asume el gasto, con
        permisos del sistema (el empleado no tiene acceso a esa empresa)."""
        self.ensure_one()
        first = expenses[0]
        company = first._l10n_pe_get_charged_company()
        journal = company._get_hr_expense_ic_journal()
        notes = []
        date = self.accounting_date or fields.Date.context_today(self)
        lines = []
        for expense in expenses:
            product, source = company._get_hr_expense_ic_product(expense.product_id)
            if source == 'default':
                notes.append(_('%(expense)s: la categoría %(category)s no existe en %(company)s ni tiene equivalencia; '
                               'se usó el producto por defecto %(product)s.', expense=expense.name,
                               category=expense.product_id.display_name, company=company.name,
                               product=product.display_name))
            elif not product:
                notes.append(_('%(expense)s: la categoría %(category)s no existe en %(company)s; configure su '
                               'equivalencia o un producto por defecto (sin producto no se calcula la detracción).',
                               expense=expense.name, category=expense.product_id.display_name, company=company.name))
            taxes, missing = self._l10n_pe_get_ic_line_taxes(expense, product, company)
            if missing:
                notes.append(_('%(expense)s: no hay en %(company)s impuestos con el nombre %(taxes)s; la línea va '
                               'por el total sin impuestos.', expense=expense.name, company=company.name,
                               taxes=', '.join(missing)))
            included = missing or any(taxes.mapped('price_include'))
            line = {
                'name': expense.name,
                'product_id': product.id,
                'quantity': 1,
                'price_unit': expense.total_amount_currency if included else expense.untaxed_amount_currency,
                'tax_ids': [Command.set(taxes.ids)],
            }
            account = product and product.with_company(company).product_tmpl_id._get_product_accounts()['expense']
            if account:
                line['account_id'] = account.id
            analytic = self._l10n_pe_get_ic_analytic_distribution(expense, company)
            if analytic:
                line['analytic_distribution'] = analytic
            lines.append(Command.create(line))
        vals = {
            'move_type': 'in_invoice',
            'company_id': company.id,
            'journal_id': journal.id,
            'partner_id': first.vendor_id.id,
            'currency_id': first.currency_id.id,
            'ref': first.l10n_pe_document_reference,
            'invoice_date': first.date or date,
            'date': date,
            'l10n_latam_document_type_id': first.l10n_pe_document_type_id.id,
            'invoice_line_ids': lines,
            'l10n_pe_ic_origin_partner_id': self.company_id.partner_id.id,
            'l10n_pe_ic_origin_ref': self.name,
        }
        if journal.l10n_latam_use_documents:
            vals['l10n_latam_document_number'] = first.l10n_pe_document_reference
        if first.currency_id != company.currency_id and first.currency_rate:
            # Mismo tipo de cambio que en la empresa del informe.
            vals['invoice_currency_rate'] = 1 / first.currency_rate
        bill = self.env['account.move'].sudo().with_company(company).with_context(
            clean_context(self.env.context), default_move_type='in_invoice',
        ).create(vals)
        # Periodo cerrado en esa empresa: la fecha contable pasa al primer día abierto
        # (lo mismo que haría Odoo al publicarla), y se avisa.
        open_date = bill._get_accounting_date(date, bill._affect_tax_report())
        if open_date != date:
            bill.date = open_date
            notes.append(_('El periodo del %(date)s está cerrado en %(company)s: la factura quedó con fecha contable '
                           '%(new)s.', date=date.strftime('%d/%m/%Y'), company=company.name,
                           new=bill.date.strftime('%d/%m/%Y')))
        expected = sum(expenses.mapped('total_amount_currency'))
        if first.currency_id.compare_amounts(bill.amount_total, expected):
            notes.append(_('El total de la factura (%(bill)s) no es el del comprobante (%(receipt)s): revise los '
                           'impuestos.', bill=first.currency_id.format(bill.amount_total),
                           receipt=first.currency_id.format(expected)))
        notes += bill._l10n_pe_ic_withholding_warnings()
        bill.message_post(body=Markup('<p>%s</p>%s') % (
            _('Gasto rendido en %(origin)s: informe %(sheet)s de %(employee)s (asiento %(move)s). Revise la cuenta y '
              'los impuestos y publique la factura: al publicarla se registra la deuda con %(origin)s.',
              origin=self.company_id.name, sheet=self.name, employee=self.employee_id.name, move=ic_move.name),
            Markup('<ul>%s</ul>') % Markup().join(Markup('<li>%s</li>') % note for note in notes) if notes else '',
        ))
        return bill

    # -------------------------------------------------------------------------
    # Restablecer
    # -------------------------------------------------------------------------

    def _l10n_pe_undo_intercompany_expenses(self):
        """Anula el asiento intercompany y la factura en borrador de la otra empresa;
        si la factura ya se publicó, avisa (la anula su contadora)."""
        expenses = self.expense_line_ids.filtered(lambda expense: expense.l10n_pe_ic_move_id or expense.l10n_pe_ic_bill_res_id)
        if not expenses:
            return
        bills = self.env['account.move'].sudo().browse(expenses.mapped('l10n_pe_ic_bill_res_id')).exists()
        posted = bills.filtered(lambda bill: bill.state == 'posted')
        if posted:
            raise UserError(_(
                'No se puede restablecer: estas facturas ya se publicaron en la empresa que asume el gasto. Pida a '
                'su contadora que las anule primero:\n%s',
                '\n'.join(f'- {bill.company_id.name}: {bill.display_name}' for bill in posted),
            ))
        bills.filtered(lambda bill: bill.state == 'draft').button_cancel()
        moves = expenses.l10n_pe_ic_move_id.filtered(lambda move: move.state == 'posted')
        locked = moves.filtered(lambda move: not move._can_be_unlinked())
        if moves - locked:
            (moves - locked).button_draft()
            (moves - locked).button_cancel()
        if locked:
            today = fields.Date.context_today(self)
            locked._reverse_moves([{'date': today} for _move in locked], cancel=True)
        expenses.write({'l10n_pe_ic_move_id': False, 'l10n_pe_ic_bill_ref': False, 'l10n_pe_ic_bill_res_id': 0})
