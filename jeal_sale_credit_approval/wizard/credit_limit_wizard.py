# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError


class CreditLimitWizard(models.TransientModel):
    _name = 'sale.credit.limit.wizard'
    _description = "Cambiar límite de crédito"

    partner_id = fields.Many2one(
        'res.partner', string="Cliente", required=True)
    company_id = fields.Many2one(
        'res.company', related='partner_id.company_id')
    currency_id = fields.Many2one(
        'res.currency', related='partner_id.sca_company_currency_id')
    current_limit = fields.Monetary(
        string="Límite actual", related='partner_id.sca_credit_limit')
    debt_total = fields.Monetary(
        string="Deuda total hoy", related='partner_id.sca_debt_total')
    debt_overdue = fields.Monetary(
        string="Deuda vencida", related='partner_id.sca_debt_overdue')
    new_limit = fields.Monetary(string="Nuevo límite (S/)", required=True)
    reason = fields.Text(string="Motivo", required=True)
    new_available = fields.Monetary(
        string="Nueva línea disponible", compute='_compute_new_available')

    @api.depends('new_limit', 'debt_total')
    def _compute_new_available(self):
        for wiz in self:
            wiz.new_available = wiz.new_limit - wiz.debt_total

    def _check_can_change(self):
        admin = self.env.ref(
            'jeal_sale_credit_approval.group_sca_credit_admin',
            raise_if_not_found=False)
        is_admin = admin and admin in self.env.user.groups_id
        company = self.env.company
        is_approver = self.env.user == company.sca_credit_approver_id
        if not (is_admin or is_approver):
            raise AccessError(_(
                "Solo el aprobador y el Administrador de créditos pueden "
                "cambiar el límite de crédito de un cliente."))

    def action_confirm(self):
        self.ensure_one()
        self._check_can_change()
        if not (self.reason or '').strip():
            raise UserError(_("El motivo es obligatorio."))
        previous = self.partner_id.sca_credit_limit
        # sudo tras validar permisos: el campo y el historial están protegidos.
        self.env['sale.credit.limit.history'].sudo().create({
            'partner_id': self.partner_id.id,
            'user_id': self.env.user.id,
            'previous_limit': previous,
            'new_limit': self.new_limit,
            'reason': self.reason,
        })
        self.partner_id.sudo().write({'sca_credit_limit': self.new_limit})
        self.partner_id.message_post(body=_(
            "Límite de crédito modificado de %(old)s a %(new)s. Motivo: %(reason)s",
            old=self.currency_id.format(previous),
            new=self.currency_id.format(self.new_limit),
            reason=self.reason))
        return {'type': 'ir.actions.act_window_close'}
