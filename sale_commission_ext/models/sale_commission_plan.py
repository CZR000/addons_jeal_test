from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleCommissionPlan(models.Model):
    _inherit = 'sale.commission.plan'

    # Nativo: related a la moneda de la compañía, sin opción de otra moneda.
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related=False,
        compute='_compute_currency_id', store=True, readonly=False, precompute=True,
        required=True,
        tracking=True,
        help='Moneda de los objetivos, niveles de comisión, logros y comisiones del plan.',
    )

    @api.depends('company_id')
    def _compute_currency_id(self):
        for plan in self:
            plan.currency_id = plan.company_id.currency_id

    def write(self, vals):
        if 'currency_id' in vals:
            locked = self.filtered(lambda plan: plan.state != 'draft' and plan.currency_id.id != vals['currency_id'])
            if locked:
                raise UserError(_(
                    'La moneda solo se puede cambiar en planes en borrador: %s',
                    ', '.join(locked.mapped('name')),
                ))
        return super().write(vals)
