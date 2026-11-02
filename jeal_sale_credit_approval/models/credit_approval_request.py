# -*- coding: utf-8 -*-
import secrets
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_datetime


class CreditApprovalRequest(models.Model):
    _name = 'sale.credit.approval.request'
    _description = "Solicitud de aprobación de crédito"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string="Número", required=True, copy=False, readonly=True,
        default=lambda self: _("Nuevo"))
    order_id = fields.Many2one(
        'sale.order', string="Cotización", required=True,
        ondelete='cascade', index=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string="Cliente", required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía",
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string="Moneda")
    user_id = fields.Many2one(
        'res.users', string="Vendedor", default=lambda self: self.env.user,
        tracking=True)
    approver_id = fields.Many2one('res.users', string="Aprobador", tracking=True)

    amount_pen = fields.Monetary(string="Importe de la cotización (S/)")
    order_currency_id = fields.Many2one(
        'res.currency', string="Moneda de la cotización")
    order_amount = fields.Monetary(
        string="Importe en moneda de la cotización",
        currency_field='order_currency_id')
    debt_total = fields.Monetary(string="Deuda total")
    debt_overdue = fields.Monetary(string="Deuda vencida")
    credit_limit = fields.Monetary(string="Límite de crédito")
    excess = fields.Monetary(string="Exceso sobre el límite")
    overdue_days = fields.Integer(string="Días de atraso")
    reason_code = fields.Selection([
        ('excess', "Excede línea"),
        ('overdue', "Deuda vencida"),
        ('both', "Excede línea y deuda vencida"),
    ], string="Motivo de la solicitud", tracking=True)

    rejection_reason = fields.Text(string="Motivo del rechazo")
    state = fields.Selection([
        ('pending', "Pendiente"),
        ('approved', "Aprobada"),
        ('rejected', "Rechazada"),
        ('expired', "Vencida"),
    ], string="Estado", default='pending', tracking=True, copy=False)

    # Solo el sistema lee el token: así el vendedor no puede armar el enlace
    # de aprobación y aprobarse a sí mismo.
    token = fields.Char(string="Token", copy=False, index=True, readonly=True,
                        groups='base.group_system')
    sent_date = fields.Datetime(string="Enviada", copy=False)
    expiry_date = fields.Datetime(string="Vence", copy=False, tracking=True)
    decided_date = fields.Datetime(string="Fecha de decisión", copy=False)

    # ------------------------------------------------------------------
    # Creación
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("Nuevo")) == _("Nuevo"):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sale.credit.approval.request') or _("Nuevo")
            # El token y el estado inicial los fija siempre el sistema.
            vals['token'] = secrets.token_urlsafe(32)
            if not self.env.su:
                vals['state'] = 'pending'
                vals.pop('rejection_reason', None)
                vals.pop('decided_date', None)
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _is_valid(self):
        self.ensure_one()
        return (
            self.state == 'pending'
            and self.expiry_date
            and self.expiry_date >= fields.Datetime.now()
        )

    def _get_public_url(self, action):
        self.ensure_one()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return "%s/credit/solicitud/%s?token=%s&action=%s" % (
            base, self.name.replace('/', '-'), self.token, action)

    # ------------------------------------------------------------------
    # Textos para el correo y la página pública
    # ------------------------------------------------------------------
    def _get_reason_lines(self):
        """Motivo(s) de la solicitud en lenguaje simple."""
        self.ensure_one()
        fmt = self.currency_id.format
        lines = []
        if self.reason_code in ('excess', 'both'):
            if not self.credit_limit:
                lines.append(_("el cliente no tiene línea de crédito asignada."))
            else:
                lines.append(_(
                    "esta venta supera la línea de crédito en %(amount)s.",
                    amount=fmt(self.excess)))
        if self.reason_code in ('overdue', 'both'):
            if self.overdue_days:
                lines.append(_(
                    "el cliente tiene %(amount)s vencidos (desde hace "
                    "%(days)s días).",
                    amount=fmt(self.debt_overdue), days=self.overdue_days))
            else:
                lines.append(_(
                    "el cliente tiene %(amount)s vencidos.",
                    amount=fmt(self.debt_overdue)))
        return lines

    def _get_available_text(self):
        """Crédito disponible antes de esta venta: «X de Y»."""
        self.ensure_one()
        fmt = self.currency_id.format
        if not self.credit_limit:
            return _("Sin línea de crédito asignada")
        available = self.credit_limit - self.debt_total
        if available <= 0:
            return _("%(avail)s de %(limit)s (línea agotada)",
                     avail=fmt(0.0), limit=fmt(self.credit_limit))
        return _("%(avail)s de %(limit)s",
                 avail=fmt(available), limit=fmt(self.credit_limit))

    def _format_expiry(self):
        """Vencimiento en la zona horaria del aprobador (Lima por defecto)."""
        self.ensure_one()
        if not self.expiry_date:
            return ''
        tz = self.approver_id.tz or 'America/Lima'
        return format_datetime(self.env, self.expiry_date, tz=tz,
                               dt_format="dd/MM/yyyy 'a las' HH:mm")

    def _send_request_mail(self):
        self.ensure_one()
        template = self.env.ref(
            'jeal_sale_credit_approval.mail_tmpl_credit_request',
            raise_if_not_found=False)
        if template and self.approver_id.email:
            template.sudo().send_mail(self.id, force_send=True)
        self.sudo().write({'sent_date': fields.Datetime.now()})

    def _notify_salesperson(self, template_xmlid):
        self.ensure_one()
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template and self.user_id.email:
            template.sudo().send_mail(self.id, force_send=True)

    # ------------------------------------------------------------------
    # Decisiones
    # ------------------------------------------------------------------
    def action_approve(self):
        for req in self:
            if not req._is_valid():
                raise UserError(_("Esta solicitud ya no está vigente."))
            req.write({
                'state': 'approved',
                'approver_id': self.env.user.id,
                'decided_date': fields.Datetime.now(),
            })
            req.order_id._sca_apply_approval(req)
            amount = (req.order_currency_id.format(req.order_amount)
                      if req.order_currency_id
                      else req.currency_id.format(req.amount_pen))
            req.order_id.message_post(body=_(
                "Crédito aprobado por %(user)s (%(name)s). Importe "
                "aprobado: %(amount)s.",
                user=self.env.user.name, name=req.name, amount=amount))
            req._notify_salesperson(
                'jeal_sale_credit_approval.mail_tmpl_credit_approved')
        return True

    def action_reject(self, reason=None):
        for req in self:
            if not req._is_valid():
                raise UserError(_("Esta solicitud ya no está vigente."))
            motive = (reason or req.rejection_reason or '').strip()
            if not motive:
                raise UserError(_("El motivo del rechazo es obligatorio."))
            req.write({
                'state': 'rejected',
                'rejection_reason': motive,
                'approver_id': self.env.user.id,
                'decided_date': fields.Datetime.now(),
            })
            req.order_id._sca_apply_rejection(req)
            req.order_id.message_post(body=_(
                "Crédito rechazado por %(user)s (%(name)s). Motivo del "
                "rechazo: %(reason)s",
                user=self.env.user.name, name=req.name, reason=motive))
            req._notify_salesperson(
                'jeal_sale_credit_approval.mail_tmpl_credit_rejected')
        return True

    @api.model
    def _cron_expire_requests(self):
        now = fields.Datetime.now()
        expired = self.search([
            ('state', '=', 'pending'),
            ('expiry_date', '<', now),
        ])
        for req in expired:
            req.state = 'expired'
            req.order_id._sca_apply_expiry(req)
            req.order_id.message_post(body=_(
                "La solicitud de crédito %(name)s venció sin respuesta del "
                "aprobador. Puede reenviarla con «Reenviar solicitud».",
                name=req.name))
            req._notify_salesperson(
                'jeal_sale_credit_approval.mail_tmpl_credit_expired')
        return True
