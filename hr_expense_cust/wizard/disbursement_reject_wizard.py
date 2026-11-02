from odoo import fields, models, _
from odoo.exceptions import UserError


class DisbursementRejectWizard(models.TransientModel):
    _name = 'expense.disbursement.reject.wizard'
    _description = 'Wizard para rechazar solicitud de desembolso'

    payment_id = fields.Many2one(
        'account.payment',
        string='Solicitud de desembolso',
        required=True,
        ondelete='cascade',
    )
    reason = fields.Text(
        string='Motivo de rechazo',
        required=True,
    )

    def action_reject(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise UserError(_('Debe ingresar el motivo del rechazo.'))
        self.payment_id.complete_disbursement_rejection(self.reason.strip())
        return {'type': 'ir.actions.act_window_close'}
