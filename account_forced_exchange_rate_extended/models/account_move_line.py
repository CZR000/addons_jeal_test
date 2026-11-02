from odoo import api, fields, models


class AccountMoveLine(models.Model):
    """
    Tipo de cambio con que quedó contabilizado cada apunte.

    Odoo ya guarda ``currency_rate``, pero en convención inversa y sin exponerlo
    en las listas. Este campo lo publica en la convención comercial del módulo
    para que, al conciliar, se vea con qué tasa se contabilizó cada apunte
    candidato y se pueda comparar con la del banco.
    """

    _inherit = "account.move.line"

    exchange_rate = fields.Float(
        string="Tipo de Cambio",
        digits=0,
        compute="_compute_exchange_rate",
        help="""
            Tipo de cambio con que se contabilizó este apunte: importe en moneda
            de la compañía dividido entre el importe en su propia moneda.\n
            Si no coincide con el del banco, la conciliación generará diferencia
            de cambio.
        """,
    )

    @api.depends("balance", "amount_currency", "currency_id", "company_currency_id")
    def _compute_exchange_rate(self):
        """
        Tipo de cambio implícito del apunte, en convención comercial.
        """
        for line in self:
            converts = (
                line.currency_id
                and line.currency_id != line.company_currency_id
                and line.amount_currency
            )
            line.exchange_rate = (
                abs(line.balance / line.amount_currency) if converts else 0.0
            )
