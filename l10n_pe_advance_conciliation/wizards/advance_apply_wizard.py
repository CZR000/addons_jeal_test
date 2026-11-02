# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nPeAdvanceApplyWizard(models.TransientModel):
    _name = "l10n_pe.advance.apply.wizard"
    _description = "Aplicar anticipos"

    move_id = fields.Many2one("account.move", string="Factura", required=True)
    partner_id = fields.Many2one(
        related="move_id.commercial_partner_id", string="Cliente/Proveedor",
    )
    currency_id = fields.Many2one(
        related="move_id.currency_id", string="Moneda de la factura",
    )
    move_total = fields.Monetary(
        related="move_id.amount_total", currency_field="currency_id",
        string="Total de la factura",
    )
    advance_type = fields.Selection(
        selection=[("customer", "Anticipos de cliente"),
                   ("supplier", "Anticipos a proveedor")],
        string="Tipo",
    )
    line_ids = fields.One2many(
        "l10n_pe.advance.apply.wizard.line", "wizard_id", string="Anticipos",
    )
    total_to_apply = fields.Monetary(
        compute="_compute_totals", currency_field="currency_id",
        string="Total a aplicar",
    )
    base_to_apply = fields.Monetary(
        compute="_compute_totals", currency_field="currency_id",
        string="Base a aplicar (cuenta 122)",
    )
    new_move_total = fields.Monetary(
        compute="_compute_totals", currency_field="currency_id",
        string="Nuevo total de la factura",
    )

    @api.depends("line_ids.apply_amount", "line_ids.selected", "move_total")
    def _compute_totals(self):
        for wiz in self:
            selected = wiz.line_ids.filtered("selected")
            total = sum(selected.mapped("apply_amount"))
            base = sum(selected.mapped("base_amount"))
            wiz.total_to_apply = total
            wiz.base_to_apply = base
            wiz.new_move_total = wiz.move_total - total

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        move_id = self.env.context.get("default_move_id")
        if not move_id:
            return res
        move = self.env["account.move"].browse(move_id)
        if move.state != "draft":
            raise UserError(_("Solo se pueden aplicar anticipos en borrador."))
        atype = (
            "customer"
            if move.move_type in ("out_invoice", "out_refund")
            else "supplier"
        )
        advances = self.env["l10n_pe.advance"].search([
            ("partner_id", "=", move.commercial_partner_id.id),
            ("advance_type", "=", atype),
            ("state", "in", ("open", "partial")),
            ("company_id", "=", move.company_id.id),
        ], order="date, id")
        remaining = move.amount_total  # con IGV por cubrir
        lines = []
        for adv in advances:
            saldo_total_move = adv.currency_id._convert(
                adv.amount_total_residual, move.currency_id,
                move.company_id, move.invoice_date or move.date,
            )
            equiv = saldo_total_move
            propose = min(saldo_total_move, max(remaining, 0.0))
            # Solo se marca por defecto mientras quede factura por cubrir.
            selected = move.currency_id.compare_amounts(propose, 0.0) > 0
            lines.append((0, 0, {
                "advance_id": adv.id,
                "selected": selected,
                "saldo_base": adv.amount_residual,
                "saldo_total": adv.amount_total_residual,
                "equivalent_amount": equiv,
                "apply_amount": propose if selected else 0.0,
            }))
            if selected:
                remaining -= propose
        res.update({
            "move_id": move.id,
            "advance_type": atype,
            "line_ids": lines,
        })
        return res

    def action_apply(self):
        self.ensure_one()
        move = self.move_id
        if move.state != "draft":
            raise UserError(_("La factura ya no esta en borrador."))
        selected = self.line_ids.filtered(
            lambda l: l.selected and l.apply_amount > 0
        )
        if not selected:
            raise UserError(_("Marca al menos un anticipo con importe."))
        if move.currency_id.compare_amounts(
            self.total_to_apply, move.amount_total
        ) > 0:
            raise UserError(
                _("El total a aplicar no puede superar el total de la factura.")
            )

        MoveLine = self.env["account.move.line"].with_context(
            check_move_validity=False
        )
        rate_date = move.invoice_date or move.date
        for line in selected:
            adv = line.advance_id
            config = adv.config_id
            product = (
                (config.application_product_id or config.origin_product_id)
                if config else False
            )
            if not product:
                raise UserError(
                    _("El anticipo %s no tiene producto de aplicacion "
                      "configurado.") % adv.name
                )
            saldo_move = adv.currency_id._convert(
                adv.amount_total_residual, move.currency_id,
                move.company_id, rate_date,
            )
            if move.currency_id.compare_amounts(
                line.apply_amount, saldo_move
            ) > 0:
                raise UserError(
                    _("El importe de %s supera su saldo disponible.") % adv.name
                )

            # Impuestos segun el tipo de documento (venta / compra).
            taxes = (
                product.supplier_taxes_id
                if move.is_purchase_document(include_receipts=True)
                else product.taxes_id
            ).filtered(lambda t: t.company_id == move.company_id)

            # Base a descontar: si se aplica todo el saldo, la base exacta;
            # si es parcial, proporcional a la relacion base/total del ANTC.
            if move.currency_id.compare_amounts(
                line.apply_amount, saldo_move
            ) == 0:
                base_move = adv.currency_id._convert(
                    adv.amount_residual, move.currency_id,
                    move.company_id, rate_date,
                )
            else:
                ratio = (
                    adv.amount_base / adv.amount_total
                    if adv.amount_total else 1.0
                )
                base_move = move.currency_id.round(line.apply_amount * ratio)

            # Si los impuestos son precio-incluido va el total; si no, la base.
            price_unit = (
                line.apply_amount
                if taxes and all(t.price_include for t in taxes)
                else base_move
            )

            glosa = _("ANTICIPO: FACTURA NRO. %s") % (
                adv.origin_move_id.name or adv.name
            )
            MoveLine.create({
                "move_id": move.id,
                "product_id": product.id,
                "account_id": adv.control_account_id.id,
                "name": glosa,
                "quantity": -1.0,
                "price_unit": price_unit,
                "tax_ids": [(6, 0, taxes.ids)],
                "l10n_pe_advance_id": adv.id,
            })
        # El ORM recalcula impuestos y totales al crear las lineas. Se fuerza
        # una relectura para dejar la factura consistente antes de cerrar.
        move.invalidate_recordset(["amount_total", "amount_tax", "amount_untaxed"])
        return {"type": "ir.actions.act_window_close"}


class L10nPeAdvanceApplyWizardLine(models.TransientModel):
    _name = "l10n_pe.advance.apply.wizard.line"
    _description = "Linea de aplicacion de anticipos"
    _order = "advance_date, id"

    wizard_id = fields.Many2one(
        "l10n_pe.advance.apply.wizard", required=True, ondelete="cascade",
    )
    advance_id = fields.Many2one(
        "l10n_pe.advance", string="Anticipo", required=True,
    )
    advance_date = fields.Date(related="advance_id.date", string="Fecha")
    origin_move_id = fields.Many2one(
        related="advance_id.origin_move_id", string="Factura origen",
    )
    contract_ref = fields.Char(
        related="advance_id.contract_ref", string="Contrato",
    )
    advance_currency_id = fields.Many2one(
        related="advance_id.currency_id", string="Mon.",
    )
    move_currency_id = fields.Many2one(
        related="wizard_id.currency_id", string="Moneda factura",
    )
    selected = fields.Boolean(string="Usar")
    saldo_base = fields.Monetary(
        string="Saldo base", currency_field="advance_currency_id",
    )
    saldo_total = fields.Monetary(
        string="Saldo con IGV", currency_field="advance_currency_id",
    )
    apply_amount = fields.Monetary(
        string="Aplicar (con IGV)", currency_field="move_currency_id",
    )
    equivalent_amount = fields.Monetary(
        string="Equivalente", currency_field="move_currency_id",
    )
    base_amount = fields.Monetary(
        compute="_compute_base_amount", currency_field="move_currency_id",
        string="Base a aplicar",
    )

    @api.depends("apply_amount")
    def _compute_base_amount(self):
        for line in self:
            # Base = importe con IGV / 1.18 (IGV 18% incluido).
            line.base_amount = line.apply_amount / 1.18 if line.apply_amount else 0.0

    @api.onchange("selected")
    def _onchange_selected(self):
        for line in self:
            if not line.selected:
                line.apply_amount = 0.0
            elif not line.apply_amount:
                line.apply_amount = min(
                    line.equivalent_amount,
                    max(line.wizard_id.new_move_total + line.apply_amount, 0.0),
                )
