from odoo import _, api, fields, models, tools



class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Indica si la compañía permite el uso de comerciales
    enable_external_commercial = fields.Boolean(
        related="company_id.enable_external_commercial",
        readonly=True,
    )

    # Contacto comercial externo asignado a la orden de venta
    external_commercial_id = fields.Many2one(
        comodel_name="res.partner",
        string='Comercial',
        tracking=True,
        domain="""[
            ('company_id', 'in', [company_id, False]),
        ]""",
        help='Contacto comercial o vendedor externo no vinculado a un usuario del sistema. Se utiliza para indicar quién gestionó la venta.',
    )

    def _prepare_invoice(self):
        """
        Extiende la preparación o creacion de la factura para copiar el campo 'external_commercial_id'. hacia la factura
        """
        invoice_vals = super()._prepare_invoice()
        # Copia el valor del campo `Comercial` si hay data
        if self.external_commercial_id:
            invoice_vals["external_commercial_id"] = self.external_commercial_id.id
        return invoice_vals

    def write(self, vals):
        """
        Sincroniza el campo 'external_commercial_id' en las facturas relacionadas al guardar la orden de venta.
        Si se modifica el comercial en la orden de venta, se actualiza en todas las facturas
        relacionadas con dicha orden.
        """
        # Llamada al método de escritura del modelo base
        res = super().write(vals)

        # Verificar si el campo `external_commercial_id` esta incluido en 'vals'
        if "external_commercial_id" in vals:
            for order in self:
                # Nuevo comercial
                new_external_commercial_id = order.external_commercial_id or False
                # Si la orden tiene facturas relacionadas
                invoices_to_update = order.mapped("invoice_ids").filtered(
                    lambda inv: inv.state != "cancel"
                )

                # Iterar sobre las facturas y actualizar el Comercial
                if invoices_to_update:
                    invoices_to_update.write(
                        {
                            "external_commercial_id": (
                                new_external_commercial_id.id if new_external_commercial_id else False
                            )
                        }
                    )

        # Retornar el resultado de la operación
        return res
