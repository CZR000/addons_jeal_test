import re

from odoo import api, models

# Medio de pago (tabla 1) según la descripción de la operación bancaria: el
# cheque manda sobre «efectivo» o «depósito» («INGRESO DE EFECTIVO DEL CHEQUE»).
PAYMENT_MEANS_KEYWORDS = (
    (re.compile(r'\bCHEQUES?\b|\bCHQ\b', re.IGNORECASE), '007'),
    (re.compile(r'\bDEP[OÓ]SITOS?\b', re.IGNORECASE), '001'),
)


class PaymentMethodsCodes(models.Model):
    _inherit = 'payment.methods.codes'
    _rec_names_search = ['code', 'description']

    @api.depends('code', 'description')
    def _compute_display_name(self):
        # El contador identifica el medio de pago por su código de la tabla 1 (003, 007...).
        for means in self:
            means.display_name = f'{means.code} - {means.description}' if means.code else means.description

    @api.model
    def _l10n_pe_get_by_code(self, code):
        return self.search([('code', '=', code)], limit=1)

    @api.model
    def _l10n_pe_from_description(self, description):
        """Medio de pago que se deduce del texto de la operación bancaria (o vacío)."""
        code = next((code for pattern, code in PAYMENT_MEANS_KEYWORDS if pattern.search(description or '')), None)
        return self._l10n_pe_get_by_code(code) if code else self.browse()
