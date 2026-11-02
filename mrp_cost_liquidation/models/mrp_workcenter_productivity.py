from odoo import _, api, fields, models


class MRPWorkcenterProductivity(models.Model):
    _inherit = 'mrp.workcenter.productivity'

    labor_cost = fields.Monetary(
        string="Mano de obra",
        compute="_compute_labor_cost",
        store=True,
        currency_field="currency_id",
    )
    depreciation_cost = fields.Monetary(
        compute='_compute_extra_costs',
        store=True,
        currency_field='currency_id'
    )
    other_cost = fields.Monetary(
        compute='_compute_extra_costs',
        store=True,
        currency_field='currency_id'
    )
    extra_total_cost = fields.Monetary(
        compute='_compute_extra_costs',
        store=True,
        currency_field='currency_id'
    )

    @api.depends("total_cost")
    def _compute_labor_cost(self):
        for time in self:
            time.labor_cost = (time.total_cost or 0.0) if "total_cost" in time._fields else 0.0

    @api.depends(
        'duration',
        'workcenter_id.depreciation_costs_hour',
        'workcenter_id.other_costs_hour',
    )
    def _compute_extra_costs(self):
        for time in self:
            minutes = time.duration or 0.0
            hours = minutes / 60.0
            wc = time.workcenter_id

            time.depreciation_cost = (wc.depreciation_costs_hour or 0.0) * hours
            time.other_cost = (wc.other_costs_hour or 0.0) * hours
            time.extra_total_cost = time.depreciation_cost + time.other_cost
