# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sca_company_currency_id = fields.Many2one(
        'res.currency', compute='_compute_company_currency',
        string="Moneda de la compañía")
    sca_credit_limit = fields.Monetary(
        string="Límite de crédito",
        currency_field='sca_company_currency_id',
        tracking=True, readonly=True, copy=False,
        help="Línea de crédito del cliente en soles. 0 = sin línea: toda "
             "venta al crédito requiere aprobación.",
    )
    sca_debt_total = fields.Monetary(
        string="Deuda total", compute='_compute_credit_data',
        currency_field='sca_company_currency_id')
    sca_debt_overdue = fields.Monetary(
        string="Deuda vencida", compute='_compute_credit_data',
        currency_field='sca_company_currency_id')
    sca_debt_overdue_blocking = fields.Monetary(
        string="Deuda vencida fuera de gracia", compute='_compute_credit_data',
        currency_field='sca_company_currency_id',
        help="Deuda vencida con más atraso que los días de gracia: es la "
             "que exige aprobación.")
    sca_overdue_days = fields.Integer(
        string="Días de atraso", compute='_compute_credit_data',
        help="Días de atraso de la factura vencida más antigua.")
    sca_credit_available = fields.Monetary(
        string="Línea disponible", compute='_compute_credit_data',
        currency_field='sca_company_currency_id')
    sca_credit_usage = fields.Float(
        string="% de uso", compute='_compute_credit_data')
    sca_limit_history_ids = fields.One2many(
        'sale.credit.limit.history', 'partner_id', string="Historial de límite")
    is_sca_credit_manager = fields.Boolean(
        string="Puede gestionar crédito", compute='_compute_is_credit_manager')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(v.get('sca_credit_limit') for v in vals_list):
            raise AccessError(_(
                "El límite de crédito solo se asigna con el botón «Cambiar "
                "límite» de la pestaña Crédito del cliente."))
        return super().create(vals_list)

    def write(self, vals):
        if 'sca_credit_limit' in vals and not self.env.su:
            raise AccessError(_(
                "El límite de crédito solo se cambia con el botón «Cambiar "
                "límite» de la pestaña Crédito del cliente (queda registrado "
                "con motivo en el historial)."))
        return super().write(vals)

    def _compute_is_credit_manager(self):
        admin = self.env.ref(
            'jeal_sale_credit_approval.group_sca_credit_admin',
            raise_if_not_found=False)
        is_admin = bool(admin) and admin in self.env.user.groups_id
        is_approver = self.env.user == self.env.company.sca_credit_approver_id
        can = is_admin or is_approver
        for partner in self:
            partner.is_sca_credit_manager = can

    def _compute_company_currency(self):
        company = self.env.company
        for partner in self:
            partner.sca_company_currency_id = \
                (partner.company_id or company).currency_id

    def _sca_get_debt_components(self):
        """Devuelve la composición de la deuda total del cliente, en moneda de
        la compañía (soles). Las piezas incluidas dependen de la configuración.
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        company = self.company_id or self.env.company
        currency = company.currency_id

        # 1) Facturas pendientes de cobro + anticipos (líneas por cobrar)
        lines = self.env['account.move.line'].search([
            ('partner_id', 'child_of', self.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
        ])
        pending = sum(l.amount_residual for l in lines if l.amount_residual > 0)
        advances = -sum(l.amount_residual for l in lines if l.amount_residual < 0)
        # Deuda vencida neta: los anticipos y notas de crédito sin aplicar se
        # descuentan primero de las facturas vencidas más antiguas.
        overdue_lines = lines.filtered(
            lambda l: l.amount_residual > 0 and l.date_maturity
            and l.date_maturity < today).sorted('date_maturity')
        grace = company.sca_overdue_grace_days or 0
        credit_left = advances
        overdue = overdue_blocking = 0.0
        overdue_days = 0
        for line in overdue_lines:
            used = min(credit_left, line.amount_residual)
            credit_left -= used
            residual = line.amount_residual - used
            if currency.is_zero(residual) or residual < 0:
                continue
            days = (today - line.date_maturity).days
            overdue += residual
            if days > grace:
                overdue_blocking += residual
            overdue_days = max(overdue_days, days)
        scope = company.sca_debt_scope or 'invoices_orders'

        # 2) Facturas en borrador
        draft = 0.0
        if scope == 'all':
            draft_invoices = self.env['account.move'].search([
                ('partner_id', 'child_of', self.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'draft'),
            ])
            for inv in draft_invoices:
                draft += inv.currency_id._convert(
                    inv.amount_total, currency, company,
                    inv.invoice_date or today)

        # 3) Pedidos confirmados sin facturar (importe pendiente de facturar)
        so_unbilled = 0.0
        if scope in ('invoices_orders', 'all'):
            orders = self.env['sale.order'].search([
                ('partner_id', 'child_of', self.id),
                ('state', '=', 'sale'),
                ('invoice_status', '!=', 'invoiced'),
            ])
            for order in orders:
                remaining = order.amount_total - order.amount_invoiced
                if remaining > 0:
                    so_unbilled += order.currency_id._convert(
                        remaining, currency, company, today)

        total = pending + draft + so_unbilled - advances
        return {
            'pending': pending,
            'draft': draft,
            'so_unbilled': so_unbilled,
            'advances': advances,
            'overdue': overdue,
            'overdue_blocking': overdue_blocking,
            'overdue_days': overdue_days,
            'total': total,
        }

    @api.depends_context('company')
    def _compute_credit_data(self):
        for partner in self:
            # Límite y deuda se manejan siempre a nivel de la empresa
            # (contactos y direcciones hijas heredan los de su empresa).
            commercial = partner.commercial_partner_id or partner
            data = commercial._sca_get_debt_components()
            total = data['total']
            limit = commercial.sca_credit_limit
            partner.sca_debt_total = total
            partner.sca_debt_overdue = data['overdue']
            partner.sca_debt_overdue_blocking = data['overdue_blocking']
            partner.sca_overdue_days = data['overdue_days']
            partner.sca_credit_available = limit - total
            partner.sca_credit_usage = (total / limit * 100.0) if limit else 0.0

    def action_sca_change_limit(self):
        """Abre el wizard para cambiar el límite de crédito con motivo."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Cambiar límite de crédito"),
            'res_model': 'sale.credit.limit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }
