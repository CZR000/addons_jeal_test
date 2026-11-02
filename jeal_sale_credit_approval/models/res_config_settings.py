# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .res_company import SCA_LINK_VALIDITY


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sca_credit_approver_id = fields.Many2one(
        related='company_id.sca_credit_approver_id', readonly=False)
    sca_link_validity = fields.Selection(
        SCA_LINK_VALIDITY, string="Vigencia del enlace",
        compute='_compute_sca_link_validity', readonly=False)
    sca_require_approval_overdue = fields.Boolean(
        related='company_id.sca_require_approval_overdue', readonly=False)
    sca_overdue_grace_days = fields.Integer(
        related='company_id.sca_overdue_grace_days', readonly=False)
    sca_debt_scope = fields.Selection(
        related='company_id.sca_debt_scope', readonly=False)

    @api.depends('company_id')
    def _compute_sca_link_validity(self):
        valid = dict(SCA_LINK_VALIDITY)
        for settings in self:
            hours = str(settings.company_id.sca_link_validity_hours or 72)
            settings.sca_link_validity = hours if hours in valid else '72'

    def set_values(self):
        super().set_values()
        for settings in self:
            if settings.sca_link_validity:
                settings.company_id.sca_link_validity_hours = int(
                    settings.sca_link_validity)
