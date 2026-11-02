# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nPeAdvanceRevolvingWizard(models.TransientModel):
    _name = "l10n_pe.advance.revolving.wizard"
    _description = "Aplicar revolvente"

    move_id = fields.Many2one("account.move", string="Factura", required=True)
    partner_id = fields.Many2one(
        related="move_id.commercial_partner_id", string="Cliente",
    )
    currency_id = fields.Many2one(
        related="move_id.currency_id", string="Moneda",
    )
    company_id = fields.Many2one(
        related="move_id.company_id", string="Compania",
    )
    date = fields.Date(
        string="Fecha de compensacion", required=True,
        default=fields.Date.context_today,
    )
    amount_to_compensate = fields.Monetary(
        string="Importe a compensar", currency_field="currency_id",
        help="Por defecto el saldo pendiente de la factura (neto de la "
             "detraccion). Puede bajarse para una compensacion parcial; al "
             "cambiarlo se vuelve a repartir por FIFO.",
    )
    invoice_residual = fields.Monetary(
        string="Saldo de la factura", currency_field="currency_id", readonly=True,
    )
    journal_id = fields.Many2one(
        "account.journal", string="Diario", readonly=True,
    )
    line_ids = fields.One2many(
        "l10n_pe.advance.revolving.wizard.line", "wizard_id",
        string="Revolventes",
    )
    total_used = fields.Monetary(
        compute="_compute_total_used", currency_field="currency_id",
        string="Total a usar",
    )
    available_total = fields.Monetary(
        compute="_compute_total_used", currency_field="currency_id",
        string="Revolvente disponible",
    )

    @api.depends("line_ids.amount_used", "line_ids.saldo")
    def _compute_total_used(self):
        for wiz in self:
            wiz.total_used = sum(wiz.line_ids.mapped("amount_used"))
            wiz.available_total = sum(wiz.line_ids.mapped("saldo"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _get_revolving_config(self, move):
        config = self.env["l10n_pe.advance.config"]._get_config(
            "revolving", currency=move.currency_id, company=move.company_id,
        )
        if not config:
            raise UserError(_(
                "No hay configuracion de revolvente en %s para la compania "
                "%s. El revolvente solo se aplica sobre facturas en la moneda "
                "del revolvente.",
                move.currency_id.name, move.company_id.name,
            ))
        if not config.compensation_journal_id:
            raise UserError(
                _("Configura el diario de compensacion del revolvente.")
            )
        return config

    @api.model
    def _fifo_distribution(self, saldos, amount, currency):
        """Reparte `amount` sobre la lista de saldos (ya en orden FIFO)."""
        remaining = amount
        result = []
        for saldo in saldos:
            use = min(saldo, max(remaining, 0.0))
            use = currency.round(use)
            result.append(use)
            remaining -= use
        return result

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        move_id = self.env.context.get("default_move_id")
        if not move_id:
            return res
        move = self.env["account.move"].browse(move_id)
        if move.move_type != "out_invoice":
            raise UserError(
                _("El revolvente solo se aplica sobre facturas de cliente.")
            )
        if move.state != "posted":
            raise UserError(
                _("El revolvente se aplica sobre facturas publicadas.")
            )
        config = self._get_revolving_config(move)
        revolvings = self.env["l10n_pe.advance"].search([
            ("partner_id", "=", move.commercial_partner_id.id),
            ("advance_type", "=", "revolving"),
            ("state", "in", ("open", "partial")),
            ("company_id", "=", move.company_id.id),
            ("currency_id", "=", move.currency_id.id),
        ], order="date, id")
        if not revolvings:
            raise UserError(
                _("El cliente no tiene revolvente disponible en %s.")
                % move.currency_id.name
            )
        # Saldo neto: lo que queda por cobrar despues de la detraccion.
        residual = move.amount_residual
        uses = self._fifo_distribution(
            revolvings.mapped("amount_residual"), residual, move.currency_id,
        )
        lines = [
            (0, 0, {"advance_id": rev.id, "amount_used": use})
            for rev, use in zip(revolvings, uses)
        ]
        res.update({
            "move_id": move.id,
            "invoice_residual": residual,
            "amount_to_compensate": min(
                residual, sum(revolvings.mapped("amount_residual"))
            ),
            "journal_id": config.compensation_journal_id.id,
            "line_ids": lines,
        })
        return res

    @api.onchange("amount_to_compensate")
    def _onchange_amount_to_compensate(self):
        """Cambiar el importe vuelve a repartir por FIFO."""
        for wiz in self:
            lines = wiz.line_ids.sorted(lambda l: (l.advance_date, l.advance_id.id))
            uses = self._fifo_distribution(
                lines.mapped("saldo"), wiz.amount_to_compensate or 0.0,
                wiz.currency_id or wiz.env.company.currency_id,
            )
            for line, use in zip(lines, uses):
                line.amount_used = use

    # ------------------------------------------------------------------
    # Action
    # ------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        move = self.move_id
        company = move.company_id
        currency = move.currency_id
        if move.state != "posted":
            raise UserError(_("La factura ya no esta publicada."))
        if currency.compare_amounts(self.amount_to_compensate, 0.0) <= 0:
            raise UserError(_("El importe a compensar debe ser mayor a cero."))
        if currency.compare_amounts(
            self.amount_to_compensate, move.amount_residual
        ) > 0:
            raise UserError(
                _("El importe a compensar no puede superar el saldo de la "
                  "factura.")
            )
        if currency.compare_amounts(
            self.total_used, self.amount_to_compensate
        ) != 0:
            raise UserError(
                _("El total a usar debe ser igual al importe a compensar.")
            )
        used_lines = self.line_ids.filtered(
            lambda l: currency.compare_amounts(l.amount_used, 0.0) > 0
        )
        if not used_lines:
            raise UserError(_("Indica el importe a usar de cada revolvente."))
        for line in used_lines:
            if currency.compare_amounts(line.amount_used, line.saldo) > 0:
                raise UserError(
                    _("El importe de %s supera su saldo disponible.")
                    % line.advance_id.name
                )

        # Lineas por cobrar abiertas de la factura (puede haber varias
        # cuotas). Todas deben estar en la misma cuenta.
        receivable_lines = move.line_ids.filtered(
            lambda l: l.account_id.account_type == "asset_receivable"
            and not l.reconciled
        )
        if not receivable_lines:
            raise UserError(
                _("La factura no tiene un apunte por cobrar pendiente.")
            )
        receivable_account = receivable_lines.mapped("account_id")
        if len(receivable_account) > 1:
            raise UserError(
                _("La factura tiene saldos por cobrar en varias cuentas; "
                  "compensa manualmente.")
            )

        rate_date = self.date
        move_lines_cmd = []
        for line in used_lines:
            rev = line.advance_id
            balance = currency._convert(
                line.amount_used, company.currency_id, company, rate_date,
            )
            move_lines_cmd.append((0, 0, {
                "name": _("Aplicacion %s") % rev.name,
                "account_id": rev.control_account_id.id,
                "partner_id": self.partner_id.id,
                "currency_id": currency.id,
                "amount_currency": line.amount_used,   # debe
                "debit": balance,
                "credit": 0.0,
                "l10n_pe_advance_id": rev.id,
            }))
        total_balance = sum(
            company.currency_id.round(cmd[2]["debit"]) for cmd in move_lines_cmd
        )
        move_lines_cmd.append((0, 0, {
            "name": _("COMPENSACION REVOLVENTE %s") % move.name,
            "account_id": receivable_account.id,
            "partner_id": self.partner_id.id,
            "currency_id": currency.id,
            "amount_currency": -self.amount_to_compensate,   # haber
            "debit": 0.0,
            "credit": total_balance,
        }))

        comp_move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.journal_id.id,
            "date": self.date,
            "ref": _("COMPENSACION REVOLVENTE %s - %s") % (
                move.name, self.partner_id.name,
            ),
            "l10n_pe_compensated_invoice_id": move.id,
            "line_ids": move_lines_cmd,
        })
        comp_move.action_post()

        Application = self.env["l10n_pe.advance.application"].sudo()
        # Conciliar cada linea de la cuenta de control con su deposito.
        for line in used_lines:
            rev = line.advance_id
            comp_line = comp_move.line_ids.filtered(
                lambda l: l.l10n_pe_advance_id == rev
            )[:1]
            deposit_line = rev._get_open_control_line()
            full_reconcile = False
            if comp_line and deposit_line and not comp_line.reconciled:
                (comp_line + deposit_line).sudo().reconcile()
                full_reconcile = comp_line.full_reconcile_id.id
            Application.create({
                "advance_id": rev.id,
                "move_id": comp_move.id,
                "invoice_id": move.id,
                "move_line_id": comp_line.id if comp_line else False,
                "date": self.date,
                "application_type": "compensation",
                "amount_base": line.amount_used,
                "amount_total": line.amount_used,
                "amount_company_currency": abs(comp_line.balance) if comp_line else 0.0,
                "full_reconcile_id": full_reconcile,
            })

        # Conciliar la cuenta por cobrar de la compensacion con la factura.
        comp_receivable = comp_move.line_ids.filtered(
            lambda l: l.account_id == receivable_account
        )
        (comp_receivable + receivable_lines).sudo().reconcile()

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": comp_move.id,
            "view_mode": "form",
        }


class L10nPeAdvanceRevolvingWizardLine(models.TransientModel):
    _name = "l10n_pe.advance.revolving.wizard.line"
    _description = "Linea de aplicacion de revolvente"
    _order = "advance_date, id"

    wizard_id = fields.Many2one(
        "l10n_pe.advance.revolving.wizard", required=True, ondelete="cascade",
    )
    advance_id = fields.Many2one(
        "l10n_pe.advance", string="Revolvente", required=True,
    )
    advance_date = fields.Date(related="advance_id.date", string="Fecha")
    origin_move_id = fields.Many2one(
        related="advance_id.origin_move_id", string="Asiento de deposito",
    )
    currency_id = fields.Many2one(
        related="wizard_id.currency_id", string="Moneda",
    )
    deposit_amount = fields.Monetary(
        related="advance_id.amount_base", string="Deposito",
        currency_field="currency_id",
    )
    saldo = fields.Monetary(
        related="advance_id.amount_residual", string="Saldo",
        currency_field="currency_id",
    )
    amount_used = fields.Monetary(
        string="Usar", currency_field="currency_id",
    )
    saldo_after = fields.Monetary(
        compute="_compute_saldo_after", string="Saldo despues",
        currency_field="currency_id",
    )

    @api.depends("amount_used", "saldo")
    def _compute_saldo_after(self):
        for line in self:
            line.saldo_after = line.saldo - line.amount_used
