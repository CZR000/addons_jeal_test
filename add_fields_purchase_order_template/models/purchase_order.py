from odoo import _, api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # MEJORA NOMBRE CAMPO - partner_bank_id
    account_number_partner_id = fields.Many2one(
        comodel_name="res.partner.bank",
        string="Cuenta Bancaria del Proveedor",
        compute="_compute_partner_bank_id",
        store=True,
        readonly=False,
        domain="[('partner_id', '=', partner_id)]",
        tracking=True,
        help="Cuenta bancaria a la que se realizará el pago de esta orden de compra.",
    )

    # MEJORA NOMBRE CAMPO - partner_bank_currency_id
    currency_partner_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda del Banco",
        related="account_number_partner_id.currency_id",
        help="Moneda configurada en la cuenta bancaria del proveedor.",
    )

    @api.depends("partner_id")
    def _compute_partner_bank_id(self):
        """
        Calcula la cuenta bancaria basada en el proveedor.
        """
        for order in self:
            if order.partner_id:
                # Autocompleta con el primer banco del proveedor
                # Si el proveedor no tiene bancos, se asigna False
                order.account_number_partner_id = (
                    order.partner_id.bank_ids[:1]
                    if order.partner_id.bank_ids
                    else False
                )
            else:
                # Limpia el campo si se elimina el proveedor
                order.account_number_partner_id = False
