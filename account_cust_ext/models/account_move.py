from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    @staticmethod
    def _l10n_pe_prepare_destination_line(
        line, account_id, amount_currency, debit, credit
    ):
        """
        Override para propagar el product_id al asiento de destino (AED).
        El método original en l10n_pe_destination_account no incluye product_id,
        por lo que el producto no aparecía en los apuntes contables del AED.
        """
        # El método original retorna una tupla ORM: (0, 0, {vals_dict})
        cmd = (
            0,
            0,
            {
                "name": line.name,
                "account_id": account_id,
                "date": line.date,
                "amount_currency": amount_currency,
                "currency_id": line.currency_id.id,
                "debit": debit,
                "credit": credit,
                "serie_correlative": line.serie_correlative,
                "l10n_latam_document_type_id": (
                    line.l10n_latam_document_type_id.id
                    if line.l10n_latam_document_type_id
                    else False
                ),
                "partner_id": line.partner_id.id if line.partner_id else False,
                "product_id": line.product_id.id if line.product_id else False,
            },
        )
        return cmd
