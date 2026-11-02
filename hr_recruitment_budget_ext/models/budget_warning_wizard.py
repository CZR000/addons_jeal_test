from odoo import fields, models


class BudgetWarningWizard(models.TransientModel):
    _name = 'budget.warning.wizard'
    _description = 'Alerta de Presupuesto Excedido'

    message = fields.Html(string='Detalle', readonly=True)
