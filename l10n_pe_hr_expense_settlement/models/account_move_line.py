from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends_context('l10n_pe_advance_display')
    def _compute_display_name(self):
        if not self.env.context.get('l10n_pe_advance_display'):
            return super()._compute_display_name()
        # Selector de anticipos del informe: número, fecha, moneda y saldo.
        for line in self:
            line.display_name = '%s · %s · %s' % (
                line.move_id.name,
                line.date.strftime('%d/%m/%Y'),
                line.currency_id.format(line.amount_residual_currency),
            )

    def _l10n_pe_get_advance_kind(self):
        """Tipo de anticipo (entrega a rendir o fondo de caja chica) según la
        solicitud de aprobación que originó el pago (vacío si no hay apunte)."""
        return self[:1].move_id.origin_payment_id.approval_request_id.l10n_pe_advance_kind
