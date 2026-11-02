from odoo import _, api, fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    no_generate_destinations = fields.Boolean(
        string="No generar destinos",
        default=False,
        help=_(
            "Si está activo, los asientos/facturas creados con este diario NO generarán "
            "asientos de destino, aunque las cuentas contables o cuentas analíticas tengan "
            "configuración de destino."
        ),
    )
