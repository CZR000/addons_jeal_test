# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nPeAdvance(models.Model):
    _name = "l10n_pe.advance"
    _description = "Anticipo / Revolvente"
    _order = "date, id"

    name = fields.Char(
        string="Documento", required=True, copy=False, readonly=True,
        index=True, default=lambda self: _("Nuevo"),
    )
    advance_type = fields.Selection(
        selection=[
            ("customer", "Anticipo de cliente"),
            ("supplier", "Anticipo a proveedor"),
            ("revolving", "Revolvente"),
        ],
        string="Tipo", required=True, readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner", string="Socio", required=True, readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency", string="Moneda", required=True, readonly=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Compania", required=True, readonly=True,
        default=lambda self: self.env.company,
    )
    date = fields.Date(
        string="Fecha", required=True, readonly=True,
        default=fields.Date.context_today,
    )
    config_id = fields.Many2one(
        "l10n_pe.advance.config", string="Configuracion", readonly=True,
    )
    control_account_id = fields.Many2one(
        "account.account", string="Cuenta de control", readonly=True,
    )
    origin_move_id = fields.Many2one(
        "account.move", string="Asiento origen", readonly=True,
        help="Factura de anticipo o asiento del deposito.",
    )
    origin_line_id = fields.Many2one(
        "account.move.line", string="Apunte origen", readonly=True,
        index=True, copy=False,
        help="Apunte exacto de la cuenta de control que origina el saldo "
             "(linea del deposito en el revolvente). Es el apunte contra el "
             "que se concilian las aplicaciones.",
    )
    contract_ref = fields.Char(string="Contrato", readonly=True)

    amount_base = fields.Monetary(
        string="Base (cuenta control)", currency_field="currency_id", readonly=True,
    )
    amount_tax = fields.Monetary(
        string="IGV", currency_field="currency_id", readonly=True,
    )
    amount_total = fields.Monetary(
        string="Total con IGV", currency_field="currency_id", readonly=True,
    )
    amount_applied = fields.Monetary(
        string="Aplicado", currency_field="currency_id",
        compute="_compute_amounts", store=True,
    )
    amount_residual = fields.Monetary(
        string="Saldo por aplicar", currency_field="currency_id",
        compute="_compute_amounts", store=True,
    )
    amount_total_residual = fields.Monetary(
        string="Saldo con IGV", currency_field="currency_id",
        compute="_compute_amounts", store=True,
        help="Saldo por aplicar expresado con IGV.",
    )
    state = fields.Selection(
        selection=[
            ("open", "Abierto"),
            ("partial", "Parcial"),
            ("applied", "Aplicado"),
        ],
        string="Estado", compute="_compute_amounts", store=True,
    )
    application_ids = fields.One2many(
        "l10n_pe.advance.application", "advance_id", string="Aplicaciones",
    )
    application_count = fields.Integer(
        string="N. aplicaciones", compute="_compute_application_count",
    )
    note = fields.Text(string="Notas")

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends(
        "amount_base", "amount_total",
        "application_ids.amount_base", "application_ids.active",
    )
    def _compute_amounts(self):
        for rec in self:
            applied = sum(
                rec.application_ids.filtered("active").mapped("amount_base")
            )
            residual = rec.amount_base - applied
            rec.amount_applied = applied
            rec.amount_residual = residual
            # Saldo con IGV proporcional a la base.
            if rec.amount_base:
                factor = rec.amount_total / rec.amount_base
            else:
                factor = 1.0
            rec.amount_total_residual = residual * factor
            currency = rec.currency_id or self.env.company.currency_id
            if not rec.amount_base:
                rec.state = "open"
            elif currency.compare_amounts(residual, 0.0) <= 0:
                rec.state = "applied"
            elif applied:
                rec.state = "partial"
            else:
                rec.state = "open"

    @api.depends("application_ids")
    def _compute_application_count(self):
        for rec in self:
            rec.application_count = len(rec.application_ids)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nuevo")) == _("Nuevo"):
                code = (
                    "l10n_pe.revolving"
                    if vals.get("advance_type") == "revolving"
                    else "l10n_pe.advance"
                )
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code(code) or _("Nuevo")
                )
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_open_applications(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aplicaciones de %s") % self.name,
            "res_model": "l10n_pe.advance.application",
            "view_mode": "list,form",
            "domain": [("advance_id", "=", self.id)],
            "context": {"default_advance_id": self.id},
        }

    def action_open_origin_move(self):
        self.ensure_one()
        if not self.origin_move_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.origin_move_id.id,
            "view_mode": "form",
        }

    def action_open_statement(self):
        """Imprime el estado de cuenta (detalle de aplicaciones)."""
        self.ensure_one()
        return self.env.ref(
            "l10n_pe_advance_conciliation.action_report_advance_statement"
        ).report_action(self)

    def action_close_balance(self):
        self.ensure_one()
        if self.state == "applied":
            raise UserError(_("El documento ya esta aplicado."))
        if not self.config_id:
            raise UserError(
                _("El documento no tiene configuracion asociada; no se puede "
                  "determinar la cuenta de redondeo.")
            )
        tolerance = self.config_id.closing_tolerance
        if abs(self.amount_residual) > tolerance:
            raise UserError(
                _("El saldo (%s) supera la tolerancia configurada (%s).")
                % (self.amount_residual, tolerance)
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Cerrar saldo residual"),
            "res_model": "l10n_pe.advance.close.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_advance_id": self.id},
        }

    # ------------------------------------------------------------------
    # Estado de cuenta
    # ------------------------------------------------------------------
    def _l10n_pe_statement_rows(self, date_from=False, date_to=False):
        """Movimientos del documento para el estado de cuenta.

        Devuelve un dict con:
          - opening: saldo antes de date_from
          - rows: lista de movimientos dentro del rango, con saldo acumulado
          - closing: saldo al final del rango
          - income / applied: totales del rango
        Las fechas son opcionales (sin rango = todo el historial)."""
        self.ensure_one()
        date_from = fields.Date.to_date(date_from) if date_from else False
        date_to = fields.Date.to_date(date_to) if date_to else False
        types = dict(
            self.env["l10n_pe.advance.application"]._fields[
                "application_type"
            ].selection
        )
        origin_label = (
            _("Deposito") if self.advance_type == "revolving" else _("Anticipo")
        )
        movements = [{
            "date": self.date,
            "seq": 0,
            "movement": origin_label,
            "move": self.origin_move_id,
            "invoice": self.env["account.move"],
            "income": self.amount_base,
            "applied": 0.0,
        }]
        for app in self.application_ids.filtered("active").sorted(
            lambda a: (a.date or self.date, a.id)
        ):
            movements.append({
                "date": app.date or self.date,
                "seq": app.id,
                "movement": types.get(app.application_type, ""),
                "move": app.move_id,
                "invoice": app.invoice_id,
                "income": 0.0,
                "applied": app.amount_base,
            })
        movements.sort(key=lambda m: (m["date"], m["seq"]))

        opening = 0.0
        balance = 0.0
        rows = []
        income = applied = 0.0
        for mov in movements:
            if date_to and mov["date"] > date_to:
                continue
            delta = mov["income"] - mov["applied"]
            if date_from and mov["date"] < date_from:
                opening += delta
                balance += delta
                continue
            balance += delta
            income += mov["income"]
            applied += mov["applied"]
            rows.append(dict(mov, balance=balance))
        return {
            "opening": opening,
            "rows": rows,
            "closing": balance,
            "income": income,
            "applied": applied,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_open_control_line(self):
        """Apunte de la cuenta de control que origina el documento, aun por
        conciliar. Sirve para conciliar contra las aplicaciones.

        Si el documento guarda su apunte exacto (origin_line_id) se usa ese;
        si no (documentos antiguos o migrados), se busca en el asiento origen
        por cuenta y socio."""
        self.ensure_one()
        MoveLine = self.env["account.move.line"]
        if self.origin_line_id:
            line = self.origin_line_id
            return line if not line.reconciled else MoveLine
        if not self.origin_move_id or not self.control_account_id:
            return MoveLine
        lines = self.origin_move_id.line_ids.filtered(
            lambda l: l.account_id == self.control_account_id
            and not l.reconciled
        )
        same_partner = lines.filtered(
            lambda l: l.partner_id.commercial_partner_id
            == self.partner_id.commercial_partner_id
        )
        return (same_partner or lines)[:1]
