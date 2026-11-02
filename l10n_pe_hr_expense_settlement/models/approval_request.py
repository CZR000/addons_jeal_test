from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError


class ApprovalRequest(models.Model):
    _name = 'approval.request'
    _inherit = ['approval.request', 'l10n.pe.advance.block.mixin']

    l10n_pe_advance_kind = fields.Selection(related='category_id.l10n_pe_advance_kind')
    l10n_pe_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
        help='Moneda del anticipo: el pago sale del diario de esa moneda.',
    )
    l10n_pe_employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Empleado',
        compute='_compute_l10n_pe_employee_id', store=True, readonly=False,
        check_company=True,
        help='Empleado que recibe el anticipo y luego lo rinde.',
    )
    l10n_pe_expense_sheet_id = fields.Many2one(
        comodel_name='hr.expense.sheet',
        string='Reposición del informe',
        readonly=True,
        copy=False,
        help='Informe de gastos del fondo de caja chica cuyo total repone esta solicitud.',
    )

    @api.depends('request_owner_id')
    def _compute_l10n_pe_employee_id(self):
        for request in self:
            request.l10n_pe_employee_id = request.request_owner_id.employee_id.filtered(
                lambda employee: employee.company_id == request.company_id
            ) or request.l10n_pe_employee_id

    # -------------------------------------------------------------------------
    # Bloqueo por rendiciones pendientes
    # -------------------------------------------------------------------------

    @api.depends('l10n_pe_employee_id', 'request_owner_id', 'category_id', 'company_id', 'request_status')
    def _compute_l10n_pe_pending_advance_warning(self):
        super()._compute_l10n_pe_pending_advance_warning()

    def _l10n_pe_get_disbursement_partners(self):
        # Solo antes del pago: una solicitud ya pagada no es un nuevo desembolso.
        if not self.l10n_pe_advance_kind or self.request_status in ('approved', 'refused', 'cancel') \
                or self.payment_id:
            return self.env['res.partner']
        employee = self.l10n_pe_employee_id or self.request_owner_id.employee_id
        return employee.sudo().work_contact_id or self.request_owner_id.partner_id

    def _l10n_pe_get_disbursement_moves(self):
        return self.payment_id.move_id

    def action_confirm(self):
        self._l10n_pe_check_pending_advances()
        return super().action_confirm()

    def action_approve(self, approver=None):
        self._l10n_pe_check_pending_advances()
        return super().action_approve(approver)

    # -------------------------------------------------------------------------
    # Pago del anticipo
    # -------------------------------------------------------------------------

    def _get_payment_employee(self):
        return self.l10n_pe_employee_id or super()._get_payment_employee()

    def _get_payment_journal(self):
        journal = super()._get_payment_journal()
        if not self.l10n_pe_advance_kind:
            return journal
        currency = self.l10n_pe_currency_id or self.company_id.currency_id
        journals = journal | self.category_id.l10n_pe_payment_journal_ids
        journal = journals.filtered(lambda j: (j.currency_id or j.company_id.currency_id) == currency)[:1]
        if not journal:
            raise UserError(_(
                'El tipo de aprobación "%(category)s" no tiene un diario de pago en %(currency)s. '
                'Agréguelo en "Diarios de pago por moneda".',
                category=self.category_id.name, currency=currency.name,
            ))
        return journal

    def _get_advance_account(self):
        self.ensure_one()
        company = self.company_id
        currency = self.l10n_pe_currency_id or company.currency_id
        if self.l10n_pe_advance_kind == 'petty_cash':
            account = company._get_hr_expense_petty_cash_account(currency)
        else:
            account = company._get_hr_expense_advance_account(currency)
        if not account:
            raise UserError(_(
                'Configure las "Cuentas de entregas a rendir" de la compañía %s '
                '(Gastos > Configuración > Ajustes).', company.name,
            ))
        return account

    def _l10n_pe_set_category_approvers(self):
        """Aprobadores de una solicitud creada por código (p.ej. la reposición del
        fondo): los de la categoría, sin el propietario (Odoo no deja que apruebe
        su propia solicitud). Si no queda ninguno, se avisa en vez de dejar la
        solicitud sin aprobador (no se podría enviar)."""
        # Los aprobadores los fija el sistema: quien repone el fondo no necesita
        # permisos de configuración de aprobaciones.
        for request in self.sudo():
            owner = request.request_owner_id
            request.approver_ids.filtered(lambda approver: approver.user_id == owner).unlink()
            missing = request.category_id.approver_ids.filtered(
                lambda approver: approver.user_id != owner and approver.user_id not in request.approver_ids.user_id
            )
            request.approver_ids = [Command.create({
                'user_id': approver.user_id.id,
                'required': approver.required,
                'sequence': approver.sequence,
            }) for approver in missing]
            if not request.approver_ids:
                raise UserError(_(
                    'El tipo de aprobación "%(category)s" no tiene otro aprobador que %(owner)s, quien hace la '
                    'solicitud. Agregue un aprobador en Aprobaciones > Configuración > Tipos de aprobación.',
                    category=request.category_id.name, owner=owner.name,
                ))

    def _create_and_open_payment(self):
        action = super()._create_and_open_payment()
        if self.l10n_pe_advance_kind:
            self.env['account.payment'].browse(action['res_id'])._l10n_pe_ensure_journal_entry()
        return action

    def _prepare_payment_vals(self):
        vals = super()._prepare_payment_vals()
        if self.l10n_pe_advance_kind:
            vals.update({
                'currency_id': (self.l10n_pe_currency_id or self.company_id.currency_id).id,
                'destination_account_id': self._get_advance_account().id,
            })
        return vals
