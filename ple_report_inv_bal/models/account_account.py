from odoo import fields, models


# Tabla 7 SUNAT - Tipo de intangible (formato 3.9).
TABLA7_INTANGIBLE_TYPES = [
    ('01', '01 - Intangible adquirido'),
    ('02', '02 - Intangible en etapa de investigación'),
    ('03', '03 - Intangible en etapa de desarrollo'),
]


# Actividad del flujo de efectivo (formato 3.18).
CASH_FLOW_ACTIVITIES = [
    ('operation', 'Operación'),
    ('investment', 'Inversión'),
    ('financing', 'Financiamiento'),
]


class AccountAccount(models.Model):
    _inherit = 'account.account'

    l10n_pe_intangible_type = fields.Selection(
        TABLA7_INTANGIBLE_TYPES,
        string='Tipo de intangible (Tabla 7)',
        help='Tipo de intangible SUNAT (Tabla 7) que se informa en el '
             'formato 3.9 del Libro de Inventarios y Balances. Aplica a '
             'las cuentas 34 (Intangibles). Si se deja vacío se informa '
             '01 - Intangible adquirido.',
    )

    l10n_pe_cash_flow_activity = fields.Selection(
        CASH_FLOW_ACTIVITIES,
        string='Actividad en flujo de efectivo (3.18)',
        help='Fuerza la actividad en la que se presentan los cobros y pagos '
             'contra esta cuenta en el formato 3.18 (Estado de flujos de '
             'efectivo), como "Otros cobros / Otros pagos" de esa actividad. '
             'Uso tipico: prestamos intercompania (1699, 1422, 4699) en '
             'inversion o financiamiento. Si se deja vacio se usa la '
             'clasificacion por prefijo de cuenta. Una cuenta marcada como '
             'inversion o financiamiento no se incluye en los cambios de '
             'capital de trabajo de la conciliacion.',
    )
