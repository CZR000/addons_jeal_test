from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Entregas a rendir del plan del grupo (1413000 M.N., 1413001 M.E.).
ADVANCE_PREFIX = '1413'


class L10nPeAdvanceBlockMixin(models.AbstractModel):
    """Bloqueo de nuevos desembolsos (entrega a rendir, fondo o reposición de caja
    chica) a un empleado que tiene otro sin rendir en cualquier empresa del grupo
    (nota "Bloqueo de desembolsos con rendición pendiente", 20/10/2026)."""
    _name = 'l10n.pe.advance.block.mixin'
    _description = 'Bloqueo de desembolsos con rendición pendiente'

    l10n_pe_pending_advance_warning = fields.Html(
        string='Rendiciones pendientes',
        compute='_compute_l10n_pe_pending_advance_warning',
        sanitize=False,
    )
    l10n_pe_block_override_reason = fields.Text(
        string='Motivo de la autorización',
        copy=False,
        help='Solo para usuarios autorizados a desembolsar a un empleado con rendiciones pendientes: '
             'queda en el historial junto con quién lo autorizó.',
    )
    l10n_pe_block_override_user_id = fields.Many2one(
        comodel_name='res.users',
        string='Desembolso autorizado por',
        readonly=True, copy=False,
    )
    l10n_pe_can_override_block = fields.Boolean(compute='_compute_l10n_pe_can_override_block')

    @api.depends_context('uid')
    def _compute_l10n_pe_can_override_block(self):
        allowed = self.env.user.has_group('l10n_pe_hr_expense_settlement.group_advance_block_override')
        for record in self:
            record.l10n_pe_can_override_block = allowed

    def _compute_l10n_pe_pending_advance_warning(self):
        for record in self:
            pending = record._l10n_pe_get_pending_advance_lines()
            record.l10n_pe_pending_advance_warning = record._l10n_pe_pending_advance_html(pending) if pending else False

    # A implementar por cada modelo
    def _l10n_pe_get_disbursement_partners(self):
        """Contactos del empleado que recibe el desembolso (vacío: no aplica)."""
        return self.env['res.partner']

    def _l10n_pe_get_disbursement_company(self):
        return self.company_id

    def _l10n_pe_get_disbursement_moves(self):
        """Asientos del propio desembolso, que no cuentan como pendientes."""
        return self.env['account.move']

    # -------------------------------------------------------------------------

    def _l10n_pe_get_pending_advance_lines(self):
        self.ensure_one()
        company = self._l10n_pe_get_disbursement_company()
        partners = self._l10n_pe_get_disbursement_partners()
        if not partners or not company or not company.hr_expense_block_pending_advances:
            return self.env['account.move.line']
        return self.env['account.move.line']._l10n_pe_search_pending_advances(
            partners, company, exclude_moves=self._l10n_pe_get_disbursement_moves(),
        )

    def _l10n_pe_pending_advance_html(self, lines):
        rows = Markup().join(
            Markup('<li>%s</li>') % self.env._('%(number)s del %(date)s en %(company)s: %(amount)s, saldo por rendir %(residual)s',
                                      **line._l10n_pe_pending_advance_values())
            for line in lines
        )
        return Markup('<p>%s</p><ul class="mb-0">%s</ul>') % (_(
            'El empleado tiene rendiciones pendientes y no puede recibir un nuevo desembolso hasta rendirlas '
            '(informe de gastos contabilizado y devolución o reembolso del saldo):'), rows)

    def _l10n_pe_check_pending_advances(self):
        """Error si hay desembolsos sin rendir, salvo que un usuario autorizado
        indique el motivo (queda en el historial)."""
        for record in self:
            if record.l10n_pe_block_override_user_id:
                continue
            pending = record._l10n_pe_get_pending_advance_lines()
            if not pending:
                continue
            if record.l10n_pe_can_override_block and record.l10n_pe_block_override_reason:
                record.l10n_pe_block_override_user_id = self.env.user
                record.message_post(body=Markup('<p>%s</p>%s') % (
                    _('Desembolso autorizado por %(user)s pese a rendiciones pendientes. Motivo: %(reason)s',
                      user=self.env.user.name, reason=record.l10n_pe_block_override_reason),
                    record._l10n_pe_pending_advance_html(pending),
                ))
                continue
            partner = record._l10n_pe_get_disbursement_partners()[:1]
            details = '\n'.join(
                '- ' + self.env._('%(number)s del %(date)s en %(company)s: %(amount)s, saldo por rendir %(residual)s',
                         **line._l10n_pe_pending_advance_values())
                for line in pending
            )
            hint = _('\n\nPuede autorizarlo indicando el motivo en "Motivo de la autorización".') \
                if record.l10n_pe_can_override_block else ''
            raise UserError(_(
                'El empleado %(employee)s tiene rendiciones pendientes y no puede recibir un nuevo desembolso:\n'
                '%(details)s%(hint)s', employee=partner.name, details=details, hint=hint,
            ))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model
    def _l10n_pe_search_pending_advances(self, partners, company, exclude_moves=None):
        """Desembolsos del empleado con saldo por rendir en todas las empresas del
        grupo: débitos abiertos en sus cuentas de entregas a rendir (y del fondo de
        caja chica, si la empresa lo pide). El empleado tiene una ficha y un
        contacto por empresa: se reúnen por usuario, documento o RUC/DNI."""
        partners = self._l10n_pe_expand_employee_partners(partners)
        limit_date = fields.Date.context_today(self) - timedelta(days=company.hr_expense_block_pending_days or 0)
        lines = self.env['account.move.line'].sudo()
        for other in self.env['res.company'].sudo().search([]):
            # El código de las cuentas depende de la compañía activa.
            other = other.with_company(other)
            accounts = other._get_hr_expense_advance_accounts()
            if not other.hr_expense_advance_account_ids:
                # Sin configurar, las "14" incluirían préstamos al personal y otras.
                accounts = accounts.filtered(lambda account: account.code.startswith(ADVANCE_PREFIX))
            if company.hr_expense_block_include_petty_cash:
                accounts |= other.hr_expense_petty_cash_account_id
            if not accounts:
                continue
            lines |= lines.search([
                ('company_id', '=', other.id),
                ('partner_id', 'in', partners.ids),
                ('account_id', 'in', accounts.ids),
                ('parent_state', '=', 'posted'),
                ('balance', '>', 0),
                ('reconciled', '=', False),
                ('amount_residual', '>', 0),
                ('date', '<=', limit_date),
                ('move_id', 'not in', (exclude_moves or self.env['account.move']).ids),
            ], order='date, id')
        if not company.hr_expense_block_include_petty_cash:
            # Fondos de caja chica pagados a una cuenta de entregas a rendir.
            lines = lines.filtered(lambda line: line._l10n_pe_get_advance_kind() != 'petty_cash')
        return lines

    @api.model
    def _l10n_pe_expand_employee_partners(self, partners):
        Employee = self.env['hr.employee'].sudo().with_context(active_test=False)
        employees = Employee.search([('work_contact_id', 'in', partners.ids)])
        domain = [('work_contact_id', 'in', partners.ids)]
        if employees.user_id:
            domain = ['|', ('user_id', 'in', employees.user_id.ids)] + domain
        identifications = [i for i in employees.mapped('identification_id') if i]
        if identifications:
            domain = ['|', ('identification_id', 'in', identifications)] + domain
        employees = Employee.search(domain)
        partners = (partners | employees.work_contact_id).sudo()
        # Los anticipos suelen estar a nombre de un contacto con el DNI como documento,
        # distinto del contacto de trabajo de la ficha (que no lo tiene).
        vats = [vat for vat in partners.mapped('vat') + employees.mapped('identification_id') if vat]
        if vats:
            partners |= self.env['res.partner'].sudo().with_context(active_test=False).search([('vat', 'in', vats)])
        return partners

    def _l10n_pe_pending_advance_values(self):
        self.ensure_one()
        move = self.move_id
        request = move.origin_payment_id.approval_request_id
        if self.currency_id != self.company_currency_id:
            amount, residual = self.amount_currency, self.amount_residual_currency
        else:
            amount, residual = self.balance, self.amount_residual
        return {
            'number': ' / '.join(name for name in (request.name, move.name) if name),
            'date': self.date.strftime('%d/%m/%Y'),
            'company': self.company_id.name,
            'amount': self.currency_id.format(amount),
            'residual': self.currency_id.format(residual),
        }
