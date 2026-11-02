# -*- coding: utf-8 -*-
from odoo import fields, models


class HrRecruitmentWorkSystem(models.Model):
    _name = 'hr.recruitment.work.system'
    _description = 'Sistema de Trabajo'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)


class HrRecruitmentContractModality(models.Model):
    _name = 'hr.recruitment.contract.modality'
    _description = 'Modalidad de Contrato'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)


class HrRecruitmentWorkModality(models.Model):
    _name = 'hr.recruitment.work.modality'
    _description = 'Modalidad de Trabajo'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
