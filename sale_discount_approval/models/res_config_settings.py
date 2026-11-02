from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # --- Descuento Porcentual (%) ---
    sale_discount_max_pct_no_approval = fields.Float(
        string='Descuento % máximo sin autorización',
        digits=(5, 2),
        config_parameter='sale_discount_approval.max_discount_no_approval',
        help='Porcentaje de descuento máximo permitido directamente, sin aprobación del Gerente de Ventas. '
             'Usar 0 para requerir aprobación en cualquier descuento porcentual.',
    )
    sale_discount_max_pct_with_approval = fields.Float(
        string='Descuento % máximo con autorización',
        digits=(5, 2),
        config_parameter='sale_discount_approval.max_discount_with_approval',
        help='Porcentaje de descuento máximo permitido con aprobación del Gerente de Ventas. '
             'Debe ser mayor al límite sin autorización. Usar 0 para no limitar el máximo aprobable.',
    )

    # --- Descuento Fijo ($) ---
    sale_discount_max_fixed_no_approval = fields.Float(
        string='Descuento fijo ($) máximo sin autorización',
        digits=(10, 2),
        config_parameter='sale_discount_approval.max_discount_fixed_no_approval',
        help='Descuento fijo máximo permitido directamente. Usar 0 para desactivar la validación de descuento fijo.',
    )
    sale_discount_max_fixed_with_approval = fields.Float(
        string='Descuento fijo ($) máximo con autorización',
        digits=(10, 2),
        config_parameter='sale_discount_approval.max_discount_fixed_with_approval',
        help='Descuento fijo máximo aprobable por el Gerente de Ventas. Usar 0 para no limitar el máximo aprobable.',
    )

    @api.constrains(
        'sale_discount_max_pct_no_approval',
        'sale_discount_max_pct_with_approval',
        'sale_discount_max_fixed_no_approval',
        'sale_discount_max_fixed_with_approval',
    )
    def _check_discount_limits(self):
        for rec in self:
            no_pct = rec.sale_discount_max_pct_no_approval
            with_pct = rec.sale_discount_max_pct_with_approval
            no_fixed = rec.sale_discount_max_fixed_no_approval
            with_fixed = rec.sale_discount_max_fixed_with_approval

            if no_pct < 0:
                raise ValidationError(_('El límite de descuento % sin autorización no puede ser negativo.'))
            if with_pct < 0:
                raise ValidationError(_('El límite de descuento % con autorización no puede ser negativo.'))
            if no_fixed < 0:
                raise ValidationError(_('El límite de descuento fijo sin autorización no puede ser negativo.'))
            if with_fixed < 0:
                raise ValidationError(_('El límite de descuento fijo con autorización no puede ser negativo.'))

            # "Con autorización" debe ser mayor que "sin autorización" (o 0 = sin techo)
            if with_pct > 0 and with_pct <= no_pct:
                raise ValidationError(_(
                    'El descuento %% máximo con autorización (%.2f%%) debe ser '
                    'mayor al máximo sin autorización (%.2f%%).'
                ) % (with_pct, no_pct))

            if no_fixed > 0 and with_fixed > 0 and with_fixed <= no_fixed:
                raise ValidationError(_(
                    'El descuento fijo máximo con autorización debe ser '
                    'mayor al máximo sin autorización.'
                ))
