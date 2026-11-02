# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sca_sale_type = fields.Selection([
        ('cash', "Contado"),
        ('credit', "Crédito"),
    ], string="Tipo de venta", default='credit', tracking=True,
        help="Solo las ventas al Crédito pasan por el control de línea de "
             "crédito. El Contado tiene pago previo.")

    sca_company_currency_id = fields.Many2one(
        'res.currency', compute='_compute_sca_credit_box')
    sca_amount_pen = fields.Monetary(
        string="Esta cotización (S/)", compute='_compute_sca_credit_box',
        currency_field='sca_company_currency_id')
    sca_credit_limit = fields.Monetary(
        string="Límite de crédito", compute='_compute_sca_credit_box',
        currency_field='sca_company_currency_id')
    sca_debt_total = fields.Monetary(
        string="Deuda total", compute='_compute_sca_credit_box',
        currency_field='sca_company_currency_id')
    sca_debt_overdue = fields.Monetary(
        string="Deuda vencida", compute='_compute_sca_credit_box',
        currency_field='sca_company_currency_id')
    sca_credit_available = fields.Monetary(
        string="Disponible", compute='_compute_sca_credit_box',
        currency_field='sca_company_currency_id')
    sca_excess = fields.Monetary(
        string="Exceso", compute='_compute_sca_credit_box',
        currency_field='sca_company_currency_id')
    sca_requires_approval = fields.Boolean(
        string="Requiere aprobación", compute='_compute_sca_credit_box')

    sca_approval_state = fields.Selection([
        ('none', "Sin aprobación"),
        ('pending', "Pendiente de aprobación"),
        ('approved', "Crédito aprobado"),
        ('rejected', "Crédito rechazado"),
        ('expired', "Solicitud vencida"),
    ], string="Estado de aprobación", default='none', copy=False, tracking=True,
        readonly=True)
    sca_approved_amount = fields.Monetary(
        string="Importe aprobado", copy=False, readonly=True,
        currency_field='sca_company_currency_id')
    # Lo que cubre la aprobación: cliente, moneda e importe de la cotización.
    sca_approved_currency_id = fields.Many2one(
        'res.currency', string="Moneda aprobada", copy=False, readonly=True)
    sca_approved_amount_currency = fields.Monetary(
        string="Importe aprobado (moneda de la cotización)", copy=False,
        readonly=True, currency_field='sca_approved_currency_id')
    sca_approved_partner_id = fields.Many2one(
        'res.partner', string="Cliente aprobado", copy=False, readonly=True)
    sca_approval_valid = fields.Boolean(
        string="Aprobación vigente", compute='_compute_sca_approval_valid',
        help="La aprobación cubre la cotización actual: mismo cliente, misma "
             "moneda y un importe igual o menor al aprobado.")
    sca_request_ids = fields.One2many(
        'sale.credit.approval.request', 'order_id', string="Solicitudes")
    sca_request_count = fields.Integer(compute='_compute_request_count')

    # Campos que solo puede cambiar el flujo de aprobación (siempre vía sudo).
    _SCA_PROTECTED_FIELDS = (
        'sca_approval_state', 'sca_approved_amount', 'sca_approved_currency_id',
        'sca_approved_amount_currency', 'sca_approved_partner_id')
    # Estados en los que el vendedor no puede pasar la venta a Contado.
    _SCA_CASH_BLOCKED_STATES = ('pending', 'rejected', 'expired')

    def _sca_is_credit_manager(self):
        """Administrador de créditos o aprobador de la compañía."""
        user = self.env.user
        if user.has_group('jeal_sale_credit_approval.group_sca_credit_admin'):
            return True
        companies = self.company_id or self.env.company
        return user in companies.sca_credit_approver_id

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            for vals in vals_list:
                if (vals.get('sca_approval_state') not in (None, False, 'none')
                        or any(vals.get(f) for f in self._SCA_PROTECTED_FIELDS
                               if f != 'sca_approval_state')):
                    raise AccessError(_(
                        "El estado de aprobación de crédito solo puede "
                        "asignarlo el flujo de aprobación."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            if any(f in vals for f in self._SCA_PROTECTED_FIELDS):
                raise AccessError(_(
                    "El estado de aprobación de crédito solo puede "
                    "cambiarlo el flujo de aprobación."))
            if vals.get('sca_sale_type') == 'cash':
                blocked = self.filtered(
                    lambda o: o.sca_sale_type == 'credit'
                    and o.sca_approval_state in self._SCA_CASH_BLOCKED_STATES)
                if blocked and not blocked._sca_is_credit_manager():
                    raise UserError(_(
                        "No puede cambiar a Contado una venta con solicitud "
                        "de crédito pendiente, rechazada o vencida. Solo el "
                        "Administrador de créditos o el aprobador pueden "
                        "hacerlo."))
        return super().write(vals)

    def _compute_request_count(self):
        for order in self:
            order.sca_request_count = len(order.sca_request_ids)

    def _sca_amount_in_company_currency(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        if self.currency_id == company.currency_id:
            return self.amount_total
        return self.currency_id._convert(
            self.amount_total, company.currency_id, company,
            fields.Date.context_today(self))

    @api.depends('partner_id', 'amount_total', 'currency_id', 'sca_sale_type',
                 'sca_approval_state')
    def _compute_sca_credit_box(self):
        for order in self:
            company = order.company_id or self.env.company
            order.sca_company_currency_id = company.currency_id
            partner = order.partner_id.commercial_partner_id
            amount_pen = order._sca_amount_in_company_currency() if partner else 0.0
            limit = partner.sca_credit_limit if partner else 0.0
            debt = partner.sca_debt_total if partner else 0.0
            overdue = partner.sca_debt_overdue if partner else 0.0
            projected = debt + amount_pen
            excess = max(projected - limit, 0.0) if limit else projected

            needs = False
            if order.sca_sale_type == 'credit' and partner:
                if not limit:
                    needs = True
                elif float_compare(projected, limit,
                                   precision_rounding=company.currency_id.rounding) > 0:
                    needs = True
                if (company.sca_require_approval_overdue
                        and partner.sca_debt_overdue_blocking > 0):
                    needs = True

            order.sca_amount_pen = amount_pen
            order.sca_credit_limit = limit
            order.sca_debt_total = debt
            order.sca_debt_overdue = overdue
            order.sca_credit_available = limit - debt
            order.sca_excess = excess
            order.sca_requires_approval = needs

    @api.depends('sca_approval_state', 'partner_id', 'currency_id',
                 'amount_total', 'sca_approved_partner_id',
                 'sca_approved_currency_id', 'sca_approved_amount_currency')
    def _compute_sca_approval_valid(self):
        for order in self:
            valid = False
            if order.sca_approval_state == 'approved':
                currency = order.sca_approved_currency_id
                valid = bool(
                    order.partner_id.commercial_partner_id
                    == order.sca_approved_partner_id
                    and currency and order.currency_id == currency
                    and float_compare(
                        order.amount_total, order.sca_approved_amount_currency,
                        precision_rounding=currency.rounding) <= 0)
            order.sca_approval_valid = valid

    # ------------------------------------------------------------------
    # Bloqueo en la confirmación
    # ------------------------------------------------------------------
    def _sca_check_credit(self):
        self.ensure_one()
        if self.sca_sale_type != 'credit' or not self.sca_requires_approval:
            return
        if self.sca_approval_valid:
            return
        if self.sca_approval_state == 'approved':
            raise UserError(_(
                "La aprobación de crédito ya no cubre esta cotización: "
                "cambió el cliente o la moneda, o el importe subió por encima "
                "de lo aprobado (%(approved)s). Use el botón «Enviar "
                "solicitud al aprobador» para pedir una nueva aprobación.",
                approved=self.sca_approved_currency_id.format(
                    self.sca_approved_amount_currency)
                if self.sca_approved_currency_id else '-'))
        raise UserError(_(
            "La cotización no puede confirmarse: requiere aprobación de "
            "crédito. Use el botón «Enviar solicitud al aprobador»."))

    def action_confirm(self):
        for order in self:
            order._sca_check_credit()
        return super().action_confirm()

    # ------------------------------------------------------------------
    # Envío / reenvío de solicitud
    # ------------------------------------------------------------------
    def action_sca_open_send_wizard(self):
        self.ensure_one()
        if not self.sca_requires_approval:
            raise UserError(_("Esta cotización no requiere aprobación de crédito."))
        if self.sca_approval_valid:
            raise UserError(_("Esta cotización ya tiene una aprobación de "
                              "crédito vigente."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Se requiere aprobación de crédito"),
            'res_model': 'sale.credit.approval.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _sca_create_and_send_request(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        approver = company.sca_credit_approver_id
        if not approver:
            raise UserError(_(
                "No se ha configurado el aprobador de crédito en Ventas › "
                "Ajustes. Configúrelo antes de enviar solicitudes."))
        if not approver.email:
            raise UserError(_(
                "El aprobador de crédito no tiene correo configurado."))

        # Anula cualquier solicitud pendiente previa de esta cotización.
        self.sca_request_ids.filtered(
            lambda r: r.state == 'pending').sudo().write({'state': 'expired'})

        overdue = bool(company.sca_require_approval_overdue
                       and self.partner_id.sca_debt_overdue_blocking > 0)
        excess = self.sca_excess > 0
        reason = 'both' if (overdue and excess) else (
            'overdue' if overdue else 'excess')
        hours = company.sca_link_validity_hours or 72
        # sudo: el vendedor solo tiene lectura sobre las solicitudes.
        request = self.env['sale.credit.approval.request'].sudo().create({
            'order_id': self.id,
            'company_id': company.id,
            'partner_id': self.partner_id.commercial_partner_id.id,
            'user_id': self.user_id.id,
            'order_amount': self.amount_total,
            'order_currency_id': self.currency_id.id,
            'approver_id': approver.id,
            'amount_pen': self.sca_amount_pen,
            'debt_total': self.sca_debt_total,
            'debt_overdue': self.sca_debt_overdue,
            'overdue_days': self.partner_id.sca_overdue_days,
            'credit_limit': self.sca_credit_limit,
            'excess': self.sca_excess,
            'reason_code': reason,
            'expiry_date': fields.Datetime.now() + timedelta(hours=hours),
        })
        request._send_request_mail()
        self.sudo().write({'sca_approval_state': 'pending'})
        reasons = request._get_reason_lines()
        self.message_post(body=_(
            "Solicitud de crédito %(name)s enviada a %(approver)s. "
            "%(label)s %(reasons)s Esta venta: %(amount)s · Crédito "
            "disponible: %(available)s.",
            name=request.name, approver=approver.name,
            label=_("Motivos:") if len(reasons) > 1 else _("Motivo:"),
            reasons=" ".join(reasons),
            amount=self.currency_id.format(self.amount_total),
            available=request._get_available_text()))
        return request

    def action_sca_resend_request(self):
        self.ensure_one()
        if not self.sca_requires_approval:
            raise UserError(_("Esta cotización ya no requiere aprobación."))
        self._sca_create_and_send_request()
        return True

    # ------------------------------------------------------------------
    # Callbacks desde la solicitud
    # ------------------------------------------------------------------
    def _sca_apply_approval(self, request):
        self.ensure_one()
        # Solicitudes antiguas sin importe en moneda de la cotización: se
        # aprueba el importe actual de la cotización.
        currency = request.order_currency_id or self.currency_id
        amount = (request.order_amount if request.order_currency_id
                  else self.amount_total)
        partner = (request.partner_id or self.partner_id).commercial_partner_id
        self.sudo().write({
            'sca_approval_state': 'approved',
            'sca_approved_amount': request.amount_pen,
            'sca_approved_currency_id': currency.id,
            'sca_approved_amount_currency': amount,
            'sca_approved_partner_id': partner.id,
        })

    def _sca_apply_rejection(self, request):
        self.ensure_one()
        self.sudo().write({'sca_approval_state': 'rejected'})

    def _sca_apply_expiry(self, request):
        self.ensure_one()
        if self.sca_approval_state == 'pending':
            self.sudo().write({'sca_approval_state': 'expired'})

    def action_sca_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Solicitudes de aprobación"),
            'res_model': 'sale.credit.approval.request',
            'view_mode': 'list,form',
            'domain': [('order_id', '=', self.id)],
        }
