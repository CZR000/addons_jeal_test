from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    is_analytic_account = fields.Boolean(
        related="picking_type_id.is_analytic_account",
        string="¿Es cuenta analítica?",
    )

    show_analytic_section = fields.Boolean(
        compute="_compute_show_analytic_section",
        string="Mostrar sección analítica",
    )

    analytic_plan_id = fields.Many2one(
        comodel_name="account.analytic.plan",
        string="Plan Analítico Padre",
    )

    analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Cuenta Analítica Padre",
        domain="[('plan_id', '=', analytic_plan_id)]",
    )

    # Eliminar campos
    stock_move_line_nosuggest_ids = fields.One2many(
        comodel_name="stock.move.line",
        inverse_name="picking_id",
        string="Líneas no sugeridas",
        domain=[
            "|",
            ("picked", "=", True),
            ("quantity", "=", 0.0),
        ],
        help="Líneas de movimiento de stock que fueron agregadas manualmente o ya fueron procesadas.",
    )

    stock_move_line_ids_without_package = fields.One2many(
        "stock.move.line",
        "picking_id",
        domain=[
            "|",
            ("package_level_id", "=", False),
            ("picking_type_entire_packs", "=", False),
        ],
    )
    # Hasta aca

    # ---------------------------------------------------------------------------- #
    #                            TODO - METODOS COMPUTE                            #
    # ---------------------------------------------------------------------------- #
    @api.depends("is_analytic_account", "analytic_plan_id", "analytic_account_id")
    def _compute_show_analytic_section(self):
        for record in self:
            record.show_analytic_section = (
                record.is_analytic_account
                or record.analytic_plan_id
                or record.analytic_account_id
            )

    # ---------------------------------------------------------------------------- #
    #                                TODO - METODOS                                #
    # ---------------------------------------------------------------------------- #
    def button_add(self):
        """
        Asigna en cascada la cuenta analítica de la cabecera a todas las líneas
        """
        for record in self:
            if not record.analytic_account_id:
                raise ValidationError(
                    _("Debe especificar una cuenta analítica para este registro.")
                )

            # Escribimos en todas las líneas de un solo golpe
            record.move_line_ids.write(
                {
                    "analytic_plan_id": record.analytic_plan_id.id,
                    "analytic_id": record.analytic_account_id.id,
                }
            )

    def button_add_analytic_account(self):
        """
        Actualización Retroactiva: Aplica la analítica a los asientos contables ya generados
        """
        for record in self:
            # 1. Actualizamos las líneas logísticas
            record.button_add()

            # 2. Buscamos todas las Capas de Valoración (SVL) generadas por este Albarán
            svls = self.env["stock.valuation.layer"].search(
                [("stock_move_id.picking_id", "=", record.id)]
            )

            # 3. Iteramos las capas para actualizar el asiento contable correspondiente
            lines_to_update = self.env["account.move.line"]
            for svl in svls:
                account_output = (
                    svl.product_id.categ_id.property_stock_account_output_categ_id
                )
                if not account_output or not svl.account_move_id:
                    continue

                # Filtramos la línea del asiento que corresponde a la salida de inventario
                relevant_lines = svl.account_move_id.line_ids.filtered(
                    lambda l: l.account_id == account_output
                )
                lines_to_update |= relevant_lines

            # 4. validación contable para escribir en asientos publicados
            if lines_to_update:
                analytic_dict = {str(record.analytic_account_id.id): 100}
                lines_to_update.with_context(check_move_validity=False).write(
                    {"analytic_distribution": analytic_dict}
                )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Éxito"),
                "message": _(
                    "Se modificaron las cuentas analíticas en los asientos de valoración correctamente."
                ),
                "type": "success",
                "sticky": False,
            },
        }
