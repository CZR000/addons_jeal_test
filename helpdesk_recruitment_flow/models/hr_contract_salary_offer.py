# -*- coding: utf-8 -*-
from odoo import fields, models


class HrContractSalaryOffer(models.Model):
    _inherit = 'hr.contract.salary.offer'

    x_applicant_stage_is_carta_oferta = fields.Boolean(
        related='applicant_id.x_stage_is_carta_oferta',
    )
