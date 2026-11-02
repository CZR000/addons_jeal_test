from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    payment_id = fields.Many2one(
        'account.payment',
        string='Pago',
        compute='_compute_payment_id',
        help='Pago a proveedor generado al aprobar esta solicitud.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        category_ids = {vals['category_id'] for vals in vals_list if vals.get('category_id')}
        if category_ids:
            categories = self.env['approval.category'].browse(category_ids).filtered(
                'automated_sequence'
            )
            categories._ensure_current_month_date_range()
        return super().create(vals_list)

    @api.depends('request_status')
    def _compute_payment_id(self):
        # sudo(): approvers/requesters without accounting rights must still be
        # able to see whether a payment already exists for their request.
        payments = self.env['account.payment'].sudo().search([
            ('approval_request_id', 'in', self.ids),
        ])
        payments_by_request = {p.approval_request_id.id: p for p in payments}
        for request in self:
            request.payment_id = payments_by_request.get(request.id, False)

    def action_approve(self, approver=None):
        res = super().action_approve(approver)
        if (
            self.approval_type == 'payment'
            and self.request_status == 'approved'
            and not self.payment_id
        ):
            return self._create_and_open_payment()
        return res

    def action_view_payment(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'je_approval_expense_flow.action_view_payment_from_request'
        )
        action['res_id'] = self.payment_id.id
        action['target'] = 'current'
        return action

    def _create_and_open_payment(self):
        self.ensure_one()
        payment = self.env['account.payment'].sudo().create(self._prepare_payment_vals())

        action = self.env['ir.actions.act_window']._for_xml_id(
            'je_approval_expense_flow.action_view_payment_from_request'
        )
        action['name'] = self.name
        action['res_id'] = payment.id
        action['target'] = 'current'
        return action

    def _get_payment_journal(self):
        """Diario del pago que se crea al aprobar la solicitud."""
        self.ensure_one()
        category = self.category_id
        if not category.default_payment_journal_id:
            raise UserError(_(
                'La categoría "%s" no tiene un Diario de pago por defecto configurado. '
                'Configúrelo en Aprobaciones > Configuración > Tipos de aprobación antes '
                'de aprobar esta solicitud.'
            ) % category.name)
        return category.default_payment_journal_id

    def _get_payment_employee(self):
        """Empleado beneficiario del pago: quien hizo la solicitud."""
        self.ensure_one()
        return self.request_owner_id.employee_id

    def _prepare_payment_vals(self):
        self.ensure_one()
        category = self.category_id
        journal = self._get_payment_journal()
        employee = self._get_payment_employee()
        partner = employee.work_contact_id or self.request_owner_id.partner_id
        bank_account = employee.sudo().bank_account_id

        payment_method_line = category.default_payment_method_line_id
        if (
            not payment_method_line
            or payment_method_line.journal_id != journal
            or payment_method_line.payment_type != 'outbound'
        ):
            payment_method_line = journal.outbound_payment_method_line_ids[:1]
        if not payment_method_line:
            raise UserError(_(
                'El diario "%s" no tiene ningún método de pago de salida configurado. '
                'Configure uno en el diario, o configure el "Método de pago por defecto" '
                'en la categoría "%s" antes de aprobar esta solicitud.'
            ) % (journal.name, category.name))

        vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': partner.id,
            'amount': self.amount,
            'date': fields.Date.context_today(self),
            'memo': self.name,
            'journal_id': journal.id,
            'payment_method_line_id': payment_method_line.id,
            'partner_bank_id': bank_account.id,
            'approval_request_id': self.id,
        }
        if 'means_payment_id' in self.env['account.payment']._fields:
            # Medio de pago acorde al diario: bancario para un banco, efectivo para una caja.
            means_payment = category._get_means_payment(journal)
            if means_payment:
                vals['means_payment_id'] = means_payment.id
        return vals
