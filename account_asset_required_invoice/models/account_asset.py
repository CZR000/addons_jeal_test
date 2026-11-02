# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import ValidationError


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    def validate(self):
        """Exige al menos una línea de factura antes de confirmar el activo.
        Los modelos de activo (state = 'model') no aplican.
        Los activos auto-generados desde una factura de proveedor pasan
        de forma natural, ya que nacen con la línea.
        """
        for asset in self:
            if asset.state == 'model':
                continue
            if not asset.original_move_line_ids:
                raise ValidationError(_(
                    "El activo '%s' debe tener al menos una factura "
                    "registrada en la pestaña 'Facturas' antes de confirmarlo.",
                    asset.name or _('(sin nombre)'),
                ))
        return super().validate()