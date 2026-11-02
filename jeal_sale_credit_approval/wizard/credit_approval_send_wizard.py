# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

from ..models.res_company import SCA_LINK_VALIDITY


class CreditApprovalSendWizard(models.TransientModel):
    _name = 'sale.credit.approval.send.wizard'
    _description = "Enviar solicitud de aprobación de crédito"

    order_id = fields.Many2one('sale.order', string="Cotización", required=True)
    partner_id = fields.Many2one(related='order_id.partner_id')
    currency_id = fields.Many2one(related='order_id.sca_company_currency_id')
    credit_limit = fields.Monetary(related='order_id.sca_credit_limit')
    credit_available = fields.Monetary(related='order_id.sca_credit_available')
    debt_total = fields.Monetary(related='order_id.sca_debt_total')
    debt_overdue = fields.Monetary(related='order_id.sca_debt_overdue')
    amount_pen = fields.Monetary(related='order_id.sca_amount_pen')
    excess = fields.Monetary(related='order_id.sca_excess')
    approver_name = fields.Char(compute='_compute_approver')
    validity_label = fields.Char(compute='_compute_approver')

    @api.depends('order_id')
    def _compute_approver(self):
        labels = {int(k): v for k, v in SCA_LINK_VALIDITY}
        for wiz in self:
            company = wiz.order_id.company_id or self.env.company
            wiz.approver_name = (company.sca_credit_approver_id.name
                                 or _("(sin configurar)"))
            hours = company.sca_link_validity_hours or 72
            wiz.validity_label = labels.get(hours) or _("%s horas", hours)

    def action_send(self):
        self.ensure_one()
        self.order_id._sca_create_and_send_request()
        return {'type': 'ir.actions.act_window_close'}
