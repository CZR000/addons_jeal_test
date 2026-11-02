from odoo import fields, models

ADVANCE_KINDS = [
    ('advance', 'Entrega a rendir'),
    ('petty_cash', 'Fondo de caja chica'),
]


class ApprovalCategory(models.Model):
    _inherit = 'approval.category'

    l10n_pe_advance_kind = fields.Selection(
        selection=ADVANCE_KINDS,
        string='Anticipo al personal',
        help='El pago de las solicitudes aprobadas se registra en la cuenta de entregas a rendir '
             '(o en la del fondo de caja chica) con el empleado como socio, para luego rendirlo '
             'en un informe de gastos.',
    )
    l10n_pe_payment_journal_ids = fields.Many2many(
        comodel_name='account.journal',
        relation='approval_category_l10n_pe_payment_journal_rel',
        string='Diarios de pago por moneda',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help='Diarios para pagar solicitudes en otras monedas (p.ej. Bcp Dólares). Se usa el '
             'que tenga la moneda de la solicitud; el diario por defecto cubre su propia moneda.',
    )
