from odoo import models, fields


class HrContract(models.Model):
    _inherit = "hr.contract"

    wage = fields.Monetary(
        groups="hr_contract_wage_restriction.group_ver_sueldo",
    )


class HrContractHistory(models.Model):
    _inherit = "hr.contract.history"

    wage = fields.Monetary(
        groups="hr_contract_wage_restriction.group_ver_sueldo",
    )
