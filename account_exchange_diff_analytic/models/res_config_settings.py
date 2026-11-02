from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    exchange_diff_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        related='company_id.exchange_diff_analytic_account_id',
        string='Cuenta Analítica - Diferencia de Cambio',
        readonly=False,
        check_company=True,
        help=(
            'Cuenta analítica que se asignará automáticamente a las líneas de '
            'diferencia de cambio (ganancia/pérdida) al conciliar apuntes en moneda '
            'extranjera. Si la cuenta analítica tiene configuración de asiento de '
            'destino, se generará el asiento de destino automáticamente.'
        ),
    )
