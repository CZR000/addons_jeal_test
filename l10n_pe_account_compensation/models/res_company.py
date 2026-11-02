# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    compensation_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de compensación',
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help='Diario donde se registran los asientos de compensación. '
             'Por defecto: Provisiones varias.',
    )
    compensation_exchange_gain_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta de ganancia por diferencia de cambio',
        domain="[('deprecated', '=', False), ('company_ids', 'in', id)]",
        help='Cuenta usada cuando la compensación genera ganancia cambiaria. '
             'Por defecto: 7760000.',
    )
    compensation_exchange_loss_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta de pérdida por diferencia de cambio',
        domain="[('deprecated', '=', False), ('company_ids', 'in', id)]",
        help='Cuenta usada cuando la compensación genera pérdida cambiaria. '
             'Por defecto: 6760000.',
    )