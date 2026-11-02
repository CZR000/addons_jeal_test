from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    period_lock_ids = fields.One2many(
        'account.period.lock', 'company_id',
        string='Periodos de Bloqueo Contable',
    )
