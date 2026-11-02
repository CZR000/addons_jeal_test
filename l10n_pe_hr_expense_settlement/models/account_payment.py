from odoo import api, models


class AccountPayment(models.Model):
    _name = 'account.payment'
    _inherit = ['account.payment', 'l10n.pe.advance.block.mixin']

    @api.depends('partner_id', 'destination_account_id', 'payment_type', 'state', 'company_id')
    def _compute_l10n_pe_pending_advance_warning(self):
        super()._compute_l10n_pe_pending_advance_warning()

    def _l10n_pe_get_disbursement_partners(self):
        """Pago manual (sin solicitud) a la cuenta de entregas a rendir o del fondo de
        un empleado. Los de una solicitud ya se revisaron al enviarla y aprobarla."""
        company = self.company_id
        if self.approval_request_id or self.payment_type != 'outbound' or self.state != 'draft' \
                or not self.partner_id or not company \
                or self.destination_account_id not in company._get_hr_expense_employee_accounts():
            return self.env['res.partner']
        is_employee = self.env['hr.employee'].sudo().with_context(active_test=False).search_count(
            [('work_contact_id', '=', self.partner_id.id)], limit=1)
        return self.partner_id if is_employee else self.env['res.partner']

    def _l10n_pe_get_disbursement_moves(self):
        return self.move_id

    def action_post(self):
        self._l10n_pe_check_pending_advances()
        return super().action_post()

    def _l10n_pe_ensure_journal_entry(self):
        """Los anticipos y devoluciones deben quedar en la cuenta 14 al publicarse.
        Si el método de pago del diario no tiene cuenta de pagos/cobros pendientes,
        Odoo no genera el asiento hasta conciliar el extracto (en una caja chica,
        nunca): se registra directo contra la cuenta del banco o la caja."""
        for payment in self.filtered(lambda payment: not payment.outstanding_account_id):
            payment.outstanding_account_id = payment.journal_id.default_account_id
