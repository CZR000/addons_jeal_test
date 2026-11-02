from odoo import fields, models

RATE_POLICIES = [
    ('by_direction', 'Cobros a TC compra y pagos a TC venta'),
    ('sale', 'Siempre TC venta'),
    ('purchase', 'Siempre TC compra'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    hr_expense_rate_policy = fields.Selection(
        selection=RATE_POLICIES,
        string='Tipo de cambio de devoluciones y reembolsos',
        default='by_direction',
        required=True,
        help='Tipo de cambio de los cobros (devolución del sobrante) y pagos (reembolso al '
             'empleado) en moneda extranjera que genera la rendición de gastos.',
    )

    def _get_hr_expense_rate_type(self, payment_type):
        """Tipo de cambio ('sale' o 'purchase') de un cobro (inbound) o pago
        (outbound) en moneda extranjera de la rendición."""
        self.ensure_one()
        if self.hr_expense_rate_policy == 'by_direction':
            return 'purchase' if payment_type == 'inbound' else 'sale'
        return self.hr_expense_rate_policy
