from odoo import fields, models


class MRPWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True
    )
    depreciation_costs_hour = fields.Monetary(
        string='Depreciación por hora',
        currency_field='currency_id',
        default=0.0
    )
    other_costs_hour = fields.Monetary(
        string='Otros costos por hora',
        currency_field='currency_id',
        default=0.0
    )
