from odoo import models, fields, _
from odoo.exceptions import UserError


class SaleDiscountRejectWizard(models.TransientModel):
    _name = 'sale.discount.reject.wizard'
    _description = 'Wizard para rechazar aprobación de descuento'

    order_id = fields.Many2one(
        'sale.order',
        string='Cotización',
        required=True,
        readonly=True,
    )
    rejection_reason = fields.Text(
        string='Motivo del Rechazo',
        required=True,
        help='Indique el motivo por el cual se rechaza el descuento solicitado.',
    )

    def action_reject(self):
        self.ensure_one()
        if not self.env.user.is_sales_manager:
            raise UserError(_('Solo el Gerente de Ventas puede rechazar descuentos.'))
        self.order_id.complete_discount_rejection(self.rejection_reason)
        return {'type': 'ir.actions.act_window_close'}
