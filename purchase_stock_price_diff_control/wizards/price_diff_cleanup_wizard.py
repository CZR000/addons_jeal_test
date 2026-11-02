from odoo import _, fields, models
from odoo.exceptions import UserError


class PdiffCleanupWizard(models.TransientModel):
    _name = "pdiff.cleanup.wizard"
    _description = "Corrección de ajustes de precio duplicados"

    company_ids = fields.Many2many(
        comodel_name="res.company",
        string="Compañías",
        default=lambda self: self.env.companies,
        required=True,
    )
    date_from = fields.Date(string="Ajustes desde")
    date_to = fields.Date(string="Ajustes hasta")
    product_ids = fields.Many2many(
        comodel_name="product.product",
        string="Productos",
        help="Vacío = todos los productos.",
    )
    fix_duplicates = fields.Boolean(
        string="Corregir ajustes duplicados",
        default=True,
        help="Facturas re-publicadas que aplicaron el ajuste de precio más de una "
        "vez sobre la misma recepción. Se conserva únicamente el último.",
    )
    fix_unposted = fields.Boolean(
        string="Corregir ajustes de facturas no publicadas",
        default=True,
        help="Ajustes que siguen valorizando el inventario aunque su factura "
        "fue cancelada o devuelta a borrador.",
    )
    force_date = fields.Date(
        string="Fecha de los asientos de reversión",
        default=fields.Date.context_today,
        required=True,
        help="Los asientos de corrección se registran en esta fecha, de forma que "
        "no afecten periodos contables ya cerrados.",
    )
    state = fields.Selection(
        selection=[("draft", "Por analizar"), ("analyzed", "Analizado"), ("done", "Corregido")],
        default="draft",
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name="pdiff.cleanup.wizard.line",
        inverse_name="wizard_id",
        string="Ajustes erróneos detectados",
        readonly=True,
    )
    group_count = fields.Integer(string="Recepciones afectadas", readonly=True)
    surplus_count = fields.Integer(string="Ajustes duplicados", readonly=True)
    unposted_count = fields.Integer(string="Ajustes de facturas no publicadas", readonly=True)
    surplus_value = fields.Float(string="Valor total a revertir", readonly=True)
    product_count = fields.Integer(string="Productos afectados", readonly=True)

    # ------------------------------------------------------------------

    def _filters(self):
        """Filtros del asistente en el formato que espera la detección SQL."""
        self.ensure_one()
        date_to = self.date_to
        if date_to:
            date_to = fields.Datetime.to_datetime(date_to).replace(
                hour=23, minute=59, second=59
            )
        return {
            "company_ids": self.company_ids.ids,
            "product_ids": self.product_ids.ids,
            "date_from": fields.Datetime.to_datetime(self.date_from) if self.date_from else None,
            "date_to": date_to,
        }

    def _collect(self, limit=None):
        """Devuelve ``(groups, sobrantes, de_facturas_no_publicadas)``."""
        self.ensure_one()
        layer_model = self.env["stock.valuation.layer"].sudo()
        filters = self._filters()
        groups = []
        surplus = layer_model.browse()
        unposted = layer_model.browse()
        if self.fix_duplicates:
            groups = layer_model._pdiff_find_duplicate_groups(limit=limit, **filters)
            surplus = layer_model.browse(
                [i for _keep, extra_ids in groups for i in extra_ids]
            )
        if self.fix_unposted:
            unposted = layer_model.browse(
                layer_model._pdiff_find_unposted_adjustment_ids(limit=limit, **filters)
            ) - surplus
        return groups, surplus, unposted

    def _reload(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_analyze(self):
        """Simulación: lista los ajustes erróneos sin modificar nada."""
        self.ensure_one()
        if not (self.fix_duplicates or self.fix_unposted):
            raise UserError(_("Seleccione al menos un tipo de corrección."))
        groups, surplus, unposted = self._collect()

        self.line_ids.unlink()
        line_vals = []
        layer_model = self.env["stock.valuation.layer"].sudo()
        for keep_id, extra_ids in groups:
            keep = layer_model.browse(keep_id)
            extra = layer_model.browse(extra_ids)
            line_vals.append(
                {
                    "wizard_id": self.id,
                    "reason": "duplicate",
                    "origin_layer_id": keep.stock_valuation_layer_id.id,
                    "product_id": keep.product_id.id,
                    "company_id": keep.company_id.id,
                    "account_move_id": keep.account_move_line_id.move_id.id,
                    "keep_layer_id": keep.id,
                    "surplus_layer_ids": [(6, 0, extra.ids)],
                    "surplus_count": len(extra),
                    "surplus_value": sum(extra.mapped("value")),
                    "current_value": keep.stock_valuation_layer_id.remaining_value,
                }
            )
        # Los ajustes duplicados ya listados no se vuelven a reportar aquí.
        for layer in unposted - surplus:
            line_vals.append(
                {
                    "wizard_id": self.id,
                    "reason": "unposted",
                    "origin_layer_id": layer.stock_valuation_layer_id.id,
                    "product_id": layer.product_id.id,
                    "company_id": layer.company_id.id,
                    "account_move_id": layer.account_move_line_id.move_id.id,
                    "keep_layer_id": False,
                    "surplus_layer_ids": [(6, 0, layer.ids)],
                    "surplus_count": 1,
                    "surplus_value": layer.value,
                    "current_value": layer.stock_valuation_layer_id.remaining_value,
                }
            )
        self.env["pdiff.cleanup.wizard.line"].create(line_vals)

        to_reverse = surplus | unposted
        self.write(
            {
                "state": "analyzed",
                "group_count": len(groups),
                "surplus_count": len(surplus),
                "unposted_count": len(unposted),
                "surplus_value": sum(to_reverse.mapped("value")),
                "product_count": len(to_reverse.product_id),
            }
        )
        return self._reload()

    def action_apply(self):
        """Genera el ajuste negativo por cada ajuste erróneo."""
        self.ensure_one()
        if self.state != "analyzed":
            raise UserError(_("Primero ejecute el análisis para revisar los resultados."))
        to_reverse = self.line_ids.surplus_layer_ids
        if not to_reverse:
            raise UserError(_("No hay ajustes erróneos que corregir."))
        # Por lotes: en bases grandes una sola pasada monta una transacción enorme.
        for index in range(0, len(to_reverse), 200):
            to_reverse[index:index + 200]._pdiff_reverse_adjustments(
                description=_("Corrección de ajuste de precio duplicado"),
                force_date=self.force_date,
            )
        self.state = "done"
        return self._reload()

    def action_open_surplus_layers(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Ajustes a revertir"),
            "res_model": "stock.valuation.layer",
            "view_mode": "list,form",
            "domain": [("id", "in", self.line_ids.surplus_layer_ids.ids)],
        }


class PdiffCleanupWizardLine(models.TransientModel):
    _name = "pdiff.cleanup.wizard.line"
    _description = "Ajuste de precio erróneo detectado"
    _order = "surplus_value desc, id"

    wizard_id = fields.Many2one("pdiff.cleanup.wizard", required=True, ondelete="cascade")
    reason = fields.Selection(
        selection=[
            ("duplicate", "Ajuste duplicado (factura re-publicada)"),
            ("unposted", "Factura no publicada"),
        ],
        string="Motivo",
        readonly=True,
    )
    company_id = fields.Many2one("res.company", string="Compañía", readonly=True)
    product_id = fields.Many2one("product.product", string="Producto", readonly=True)
    origin_layer_id = fields.Many2one(
        "stock.valuation.layer", string="Capa de recepción", readonly=True
    )
    account_move_id = fields.Many2one("account.move", string="Factura", readonly=True)
    keep_layer_id = fields.Many2one(
        "stock.valuation.layer", string="Ajuste que se conserva", readonly=True
    )
    surplus_layer_ids = fields.Many2many(
        "stock.valuation.layer", string="Ajustes a revertir", readonly=True
    )
    surplus_count = fields.Integer(string="Sobrantes", readonly=True)
    surplus_value = fields.Float(string="Valor a revertir", readonly=True)
    current_value = fields.Float(string="Valor actual de la capa", readonly=True)
