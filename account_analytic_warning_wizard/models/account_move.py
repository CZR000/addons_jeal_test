# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    # Tipos de línea que nunca deben evaluarse: no representan movimiento
    # económico propio ni admiten distribución analítica en Odoo.
    _DEST_SKIP_DISPLAY_TYPES = (
        "line_section",
        "line_note",
        "tax",
        "payment_term",
        "rounding",
        "cogs",
        "epd",
    )

    def _get_lines_missing_analytic_for_destination(self):
        """
        Devuelve las líneas que:
          - pertenecen a una cuenta con `has_destination_account=True`,
          - no tienen distribución analítica,
          - representan movimiento real (no son tax/section/note/payment_term/rounding),
          - no están en cero absoluto (debit=credit=amount_currency=0).
        """
        self.ensure_one()
        if self.journal_id.no_generate_destinations:
            return self.env["account.move.line"]

        def _is_problematic(l):
            if l.display_type in self._DEST_SKIP_DISPLAY_TYPES:
                return False
            if not l.account_id.has_destination_account:
                return False
            if l.analytic_distribution:
                return False
            # Ignora líneas sin movimiento real (fantasmas)
            company_cur = l.company_currency_id or l.company_id.currency_id
            line_cur = l.currency_id or company_cur
            if (
                company_cur.is_zero(l.balance)
                and line_cur.is_zero(l.amount_currency)
            ):
                return False
            return True

        return self.line_ids.filtered(_is_problematic)

    @staticmethod
    def _format_destination_accounts_error(lines):
        names = lines.mapped("account_id.display_name")
        accounts_str = "\n".join("• " + n for n in names[:5])
        extra = _("\n(... y otras más)") if len(names) > 5 else ""
        return accounts_str + extra

    @api.constrains("line_ids")
    def _check_analytic_required_for_destination_accounts(self):
        for move in self:
            problematic = move._get_lines_missing_analytic_for_destination()
            if not problematic:
                continue
            raise ValidationError(
                _(
                    "La Distribución Analítica es obligatoria para las siguientes "
                    "cuentas configuradas con 'Usar Cuentas de Destino':\n\n%s"
                )
                % move._format_destination_accounts_error(problematic)
            )

    def _post(self, soft=True):
        # Chequeo en _post (y no en action_post) para cubrir también
        # asientos publicados desde código: pagos, conciliación, revalorización,
        # generación de asientos de destino, etc.
        for move in self:
            problematic = move._get_lines_missing_analytic_for_destination()
            if not problematic:
                continue
            raise ValidationError(
                _(
                    "No es posible publicar el asiento. Las siguientes cuentas tienen "
                    "configurado 'Usar Cuentas de Destino' y requieren Distribución "
                    "Analítica obligatoria:\n\n%s"
                )
                % move._format_destination_accounts_error(problematic)
            )
        return super()._post(soft=soft)