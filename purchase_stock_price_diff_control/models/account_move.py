from odoo import _, models
from odoo.exceptions import UserError

PURCHASE_TYPES = ("in_invoice", "in_refund", "in_receipt")


class AccountMove(models.Model):
    _inherit = "account.move"

    # ------------------------------------------------------------------
    # Núcleo del arreglo
    # ------------------------------------------------------------------

    def _pdiff_reverse_previous_adjustments(self, description=None):
        """Revierte los ajustes de precio generados por publicaciones anteriores.

        Sin esto, ``purchase_stock`` vuelve a calcular la diferencia contra
        ``layer.value / layer.quantity`` (el valor *original* de la recepción,
        que nunca cambia) y suma otra vez el ajuste completo, inflando el costo
        en cada ciclo borrador/publicar.
        """
        purchases = self.filtered(lambda move: move.move_type in PURCHASE_TYPES)
        if not purchases:
            return self.env["stock.valuation.layer"]
        layers = purchases.sudo().line_ids.stock_valuation_layer_ids
        return layers._pdiff_reverse_adjustments(description=description)

    def _post(self, soft=True):
        # Antes de que ``purchase_stock`` aplique la diferencia de precio,
        # anulamos la de la publicación anterior para que no se acumule.
        if not self.env.context.get("move_reverse_cancel"):
            self._pdiff_reverse_previous_adjustments(
                description=_("Reversión de ajuste previo (re-publicación de factura)")
            )
        return super()._post(soft=soft)

    def button_draft(self):
        self._pdiff_check_reset_to_draft()
        res = super().button_draft()
        # Una factura en borrador no debe seguir valorizando el inventario.
        self._pdiff_reverse_previous_adjustments(
            description=_("Reversión de ajuste previo (factura pasada a borrador)")
        )
        return res

    def button_cancel(self):
        res = super().button_cancel()
        self._pdiff_reverse_previous_adjustments(
            description=_("Reversión de ajuste previo (factura cancelada)")
        )
        return res

    # ------------------------------------------------------------------
    # Bloqueo opcional del reinicio a borrador
    # ------------------------------------------------------------------

    def _pdiff_check_reset_to_draft(self):
        """Impide volver a borrador facturas de proveedor ya valorizadas.

        Control opcional por compañía; el grupo
        ``group_pdiff_force_reset_to_draft`` puede saltárselo.
        """
        if self.env.su or self.env.user.has_group(
            "purchase_stock_price_diff_control.group_pdiff_force_reset_to_draft"
        ):
            return
        blocked = self.filtered(
            lambda move: move.move_type in PURCHASE_TYPES
            and move.state == "posted"
            and move.company_id.pdiff_block_reset_to_draft
            and move.sudo().line_ids.stock_valuation_layer_ids
        )
        if blocked:
            raise UserError(
                _(
                    "Las siguientes facturas de proveedor ya generaron valorización "
                    "de inventario y no pueden volver a borrador:\n\n%(names)s\n\n"
                    "Registre una nota de crédito o solicite el permiso "
                    "«Puede reiniciar a borrador facturas valorizadas».",
                    names="\n".join("- %s" % move.display_name for move in blocked),
                )
            )
