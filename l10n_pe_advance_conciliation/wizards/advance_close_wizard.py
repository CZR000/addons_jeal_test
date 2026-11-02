# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nPeAdvanceCloseWizard(models.TransientModel):
    _name = "l10n_pe.advance.close.wizard"
    _description = "Cerrar saldo residual"

    advance_id = fields.Many2one(
        "l10n_pe.advance", string="Documento", required=True,
    )
    advance_type = fields.Selection(
        related="advance_id.advance_type", string="Tipo",
    )
    partner_id = fields.Many2one(
        related="advance_id.partner_id", string="Socio",
    )
    currency_id = fields.Many2one(
        related="advance_id.currency_id", string="Moneda",
    )
    company_id = fields.Many2one(
        related="advance_id.company_id", string="Compania",
    )
    residual = fields.Monetary(
        related="advance_id.amount_residual", string="Saldo residual",
        currency_field="currency_id",
    )
    tolerance = fields.Float(
        related="advance_id.config_id.closing_tolerance", string="Tolerancia",
    )
    account_id = fields.Many2one(
        "account.account", string="Cuenta", compute="_compute_account",
    )
    analytic_distribution = fields.Json(
        string="Distribucion analitica",
        help="Obligatoria si la cuenta de redondeo usa cuentas de destino.",
    )
    analytic_precision = fields.Integer(
        default=lambda self: self.env["decimal.precision"].precision_get(
            "Percentage Analytic"
        ),
    )
    date = fields.Date(
        string="Fecha", required=True, default=fields.Date.context_today,
    )
    journal_id = fields.Many2one(
        related="advance_id.config_id.compensation_journal_id", string="Diario",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _control_sign(self):
        """Signo con el que el saldo del documento se registra en la cuenta
        de control al cerrarlo.

        - Cliente / revolvente: la cuenta de control es un pasivo (saldo
          acreedor); cerrar un saldo positivo es un DEBE en la cuenta.
        - Proveedor: la cuenta de control es un activo (saldo deudor);
          cerrar un saldo positivo es un HABER en la cuenta.
        """
        self.ensure_one()
        return -1.0 if self.advance_id.advance_type == "supplier" else 1.0

    @api.depends("advance_id", "residual")
    def _compute_account(self):
        """Por ahora (acordado con JEAL) todo cierre va a la cuenta de gasto
        por redondeo (6593004), al debe o al haber segun el tipo de documento
        y el signo del saldo. La cuenta de ingreso solo se usa si no hay
        cuenta de gasto configurada."""
        for wiz in self:
            config = wiz.advance_id.config_id
            if not config:
                wiz.account_id = False
                continue
            wiz.account_id = (
                config.rounding_expense_account_id
                or config.rounding_income_account_id
            )

    # ------------------------------------------------------------------
    # Action
    # ------------------------------------------------------------------
    def action_close(self):
        self.ensure_one()
        advance = self.advance_id
        company = advance.company_id
        config = advance.config_id
        if not config:
            raise UserError(_("El documento no tiene configuracion asociada."))
        if not self.account_id:
            raise UserError(
                _("Configura la cuenta de redondeo (gasto/ingreso).")
            )
        journal = self.journal_id or config.compensation_journal_id
        if not journal:
            raise UserError(
                _("Configura el diario de compensacion en la configuracion.")
            )
        if abs(self.residual) > config.closing_tolerance:
            raise UserError(
                _("El saldo supera la tolerancia configurada.")
            )
        if advance.currency_id.is_zero(self.residual):
            raise UserError(_("El documento no tiene saldo por cerrar."))

        residual = self.residual
        control_amount = residual * self._control_sign()
        balance = advance.currency_id._convert(
            control_amount, company.currency_id, company, self.date,
        )
        label = _("Cierre por redondeo %s") % advance.name
        control_vals = {
            "name": label,
            "account_id": advance.control_account_id.id,
            "partner_id": advance.partner_id.id,
            "currency_id": advance.currency_id.id,
            "amount_currency": control_amount,
            "debit": balance if balance > 0 else 0.0,
            "credit": -balance if balance < 0 else 0.0,
            "l10n_pe_advance_id": advance.id,
        }
        rounding_vals = {
            "name": label,
            "account_id": self.account_id.id,
            "partner_id": advance.partner_id.id,
            "currency_id": advance.currency_id.id,
            "amount_currency": -control_amount,
            "debit": -balance if balance < 0 else 0.0,
            "credit": balance if balance > 0 else 0.0,
            "analytic_distribution": self.analytic_distribution or False,
        }
        close_move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": self.date,
            "ref": label,
            "line_ids": [(0, 0, control_vals), (0, 0, rounding_vals)],
        })
        close_move.action_post()

        control_line = close_move.line_ids.filtered(
            lambda l: l.account_id == advance.control_account_id
        )[:1]
        origin_line = advance._get_open_control_line()
        full_reconcile = False
        if control_line and origin_line and not control_line.reconciled:
            (control_line + origin_line).sudo().reconcile()
            full_reconcile = control_line.full_reconcile_id.id

        self.env["l10n_pe.advance.application"].sudo().create({
            "advance_id": advance.id,
            "move_id": close_move.id,
            "move_line_id": control_line.id if control_line else False,
            "date": self.date,
            "application_type": "rounding",
            "amount_base": residual,
            "amount_total": residual,
            "amount_company_currency": abs(balance),
            "full_reconcile_id": full_reconcile,
        })
        return {"type": "ir.actions.act_window_close"}
