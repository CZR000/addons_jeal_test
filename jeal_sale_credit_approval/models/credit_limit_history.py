# -*- coding: utf-8 -*-
from odoo import fields, models


class CreditLimitHistory(models.Model):
    _name = 'sale.credit.limit.history'
    _description = "Historial de cambios de límite de crédito"
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner', string="Cliente", required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía",
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string="Moneda")
    user_id = fields.Many2one(
        'res.users', string="Usuario", default=lambda self: self.env.user)
    change_date = fields.Datetime(
        string="Fecha", default=fields.Datetime.now)
    previous_limit = fields.Monetary(string="Anterior")
    new_limit = fields.Monetary(string="Nuevo")
    reason = fields.Text(string="Motivo", required=True)
