# -*- coding: utf-8 -*-
import re
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round

_logger = logging.getLogger(__name__)

# Regex: "Detracción 12%", "detraccion 4,5 %", "Detracción 10%, saldo al contado", etc.
DETRACTION_PCT_REGEX = re.compile(
    r'[Dd]etracci[oó]n\s+(\d+(?:[.,]\d+)?)\s*%',
    re.UNICODE,
)

# Detecta la palabra "detracción" / "detraccion" en cualquier posición
DETRACTION_LABEL_REGEX = re.compile(r'[Dd]etracci[oó]n', re.UNICODE)

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_detraction = fields.Boolean(
        string='Es detracción',
        compute='_compute_is_detraction',
        store=True,
        readonly=False,
        help='Marca si este pago corresponde a la detracción de la factura origen. '
             'Se calcula automáticamente comparando el importe del pago con '
             'el importe de detracción de la factura (total × % del término de pago). '
             'Editable manualmente para corregir casos donde la detección automática falle. '
             'Los pagos marcados se excluyen al crear un pago por lote.',
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_detraction_percentage(self, payment_term):
        """Parsea el % de detracción del nombre del término de pago."""
        if not payment_term or not payment_term.name:
            return 0.0
        match = DETRACTION_PCT_REGEX.search(payment_term.name)
        if not match:
            return 0.0
        try:
            return float(match.group(1).replace(',', '.'))
        except ValueError:
            return 0.0

    def _get_source_invoice(self):
        """Devuelve la factura de proveedor origen del pago."""
        self.ensure_one()
        if self.reconciled_bill_ids:
            return self.reconciled_bill_ids[:1]
        return self.env['account.move']

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('reconciled_bill_ids', 'amount', 'currency_id')
    def _compute_is_detraction(self):
        """Marca el pago como detracción si:
        1. El término de pago de la factura menciona 'detracción' en su nombre.
        2. El amount coincide (±1) con factura.amount_total × % detracción.
        """
        for payment in self:
            invoice = payment._get_source_invoice()
            if not invoice:
                payment.is_detraction = False
                continue

            term = invoice.invoice_payment_term_id
            term_name = (term.name or '') if term else ''

            if not DETRACTION_LABEL_REGEX.search(term_name):
                payment.is_detraction = False
                continue

            pct = payment._extract_detraction_percentage(term)
            if not pct:
                payment.is_detraction = False
                continue

            expected = invoice.amount_total * pct / 100.0
            payment.is_detraction = abs(payment.amount - expected) <= 1.0

    # ------------------------------------------------------------------
    # Override acción "Crea un pago por lote"
    # ------------------------------------------------------------------
    @api.model
    def create_batch_payment(self):
        eligible = self.filtered(lambda p: not p.is_detraction)
        excluded = self - eligible

        if not eligible:
            raise UserError(_(
                "Todos los pagos seleccionados están marcados como detracción "
                "y no pueden formar parte de un pago por lote.\n\n"
                "Los pagos de detracción deben procesarse manualmente."
            ))

        result = super(AccountPayment, eligible).create_batch_payment()

        if excluded:
            batch = self.env['account.batch.payment'].browse(result.get('res_id'))
            if batch:
                batch.message_post(body=_(
                    "Se excluyeron %(count)d pago(s) de detracción del lote: %(names)s",
                    count=len(excluded),
                    names=', '.join(excluded.mapped('name')),
                ))

        return result
