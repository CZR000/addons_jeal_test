from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    mrp_production_id = fields.Many2one(
        comodel_name='mrp.production',
        string='Orden de producción',
        help='Orden de fabricación relacionada (asignación manual para fines informativos en reportes).',
        index=True,
        copy=False,
    )
