from odoo import _, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    approval_request_id = fields.Many2one(
        'approval.request',
        string='Solicitud de aprobación',
        readonly=True,
        copy=False,
        index=True,
        help='Solicitud de la app Aprobaciones que originó este pago.',
    )
    approval_confirmation_email_sent = fields.Boolean(
        default=False,
        copy=False,
        help='Evita reenviar el correo de "pago confirmado" si action_post se llama '
             'más de una vez sobre el mismo pago.',
    )

    def action_post(self):
        res = super().action_post()
        payments_to_notify = self.filtered(
            lambda p: p.approval_request_id
            and p.state != 'draft'
            and not p.approval_confirmation_email_sent
        )
        if payments_to_notify:
            action = self.env.ref(
                'je_approval_expense_flow.action_server_approval_payment_approved',
                raise_if_not_found=False,
            )
            if action:
                for payment in payments_to_notify:
                    action.with_context(
                        active_model='account.payment',
                        active_id=payment.id,
                        active_ids=payment.ids,
                    ).run()
            payments_to_notify.approval_confirmation_email_sent = True
        return res

    def action_view_approval_request(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de aprobación'),
            'res_model': 'approval.request',
            'views': [[False, 'form']],
            'res_id': self.approval_request_id.id,
            'target': 'current',
        }
