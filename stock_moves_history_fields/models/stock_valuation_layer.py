from odoo import models, fields, api


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    code_movement_type = fields.Selection(
        string="Código de movimiento",
        selection=[
            ("A", "A"),
            ("M", "M"),
            ("C", "C"),
        ],
        compute="_compute_code_movement_type",
        inverse="_inverse_code_movement_type",
        store=True,
    )

    def _edit_fields_views(self, arch, view):
        arch, view = super()._edit_fields_views(arch, view)

        if self.env.user.has_group(
            "stock_moves_history_fields.group_edit_code_movement_type"
        ):
            for node in arch.xpath("//field[@name='code_movement_type']"):
                node.set("readonly", "0")

        return arch, view

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type="form", **options):
        key = super()._get_view_cache_key(view_id, view_type, **options)
        return key + (
            self.env.user.has_group(
                "stock_moves_history_fields.group_edit_code_movement_type"
            ),
        )

    @api.depends("stock_move_id.code_movement_type")
    def _compute_code_movement_type(self):
        for valuation_layer in self:
            valuation_layer.code_movement_type = (
                valuation_layer.stock_move_id.code_movement_type or "M"
            )

    def _inverse_code_movement_type(self):
        pass
