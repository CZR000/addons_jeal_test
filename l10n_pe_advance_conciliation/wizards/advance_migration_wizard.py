# -*- coding: utf-8 -*-
"""Wizard de migracion de saldos iniciales (DISENO PRELIMINAR).

Crea documentos ANTC/REV para los saldos abiertos que ya existen en las
cuentas de control, enlazandolos a su asiento origen. Ver pendiente 10.4 del
documento de diseno: alcance y validaciones se dimensionan como fase aparte.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nPeAdvanceMigrationWizard(models.TransientModel):
    _name = "l10n_pe.advance.migration.wizard"
    _description = "Migracion de saldos iniciales de anticipos/revolventes"

    config_id = fields.Many2one(
        "l10n_pe.advance.config", string="Configuracion", required=True,
    )
    advance_type = fields.Selection(
        related="config_id.advance_type", string="Tipo",
    )
    control_account_id = fields.Many2one(
        related="config_id.control_account_id", string="Cuenta de control",
    )
    currency_id = fields.Many2one(
        related="config_id.currency_id", string="Moneda",
    )
    line_ids = fields.One2many(
        "l10n_pe.advance.migration.wizard.line", "wizard_id", string="Saldos",
    )

    def action_load_open_items(self):
        """Carga los apuntes por conciliar de la cuenta de control, agrupados
        por socio, como saldos candidatos a migrar."""
        self.ensure_one()
        account = self.control_account_id
        lines = self.env["account.move.line"].search([
            ("account_id", "=", account.id),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("company_id", "=", self.config_id.company_id.id),
        ])
        # No migrar apuntes ya representados por un documento del modulo.
        already = self.env["l10n_pe.advance"].search([
            ("control_account_id", "=", account.id),
        ]).mapped("origin_move_id")
        grouped = {}
        for aml in lines:
            if aml.move_id in already:
                continue
            key = (aml.partner_id.id, aml.move_id.id)
            grouped.setdefault(key, 0.0)
            grouped[key] += aml.amount_residual_currency
        cmd = [(5, 0, 0)]
        for (partner_id, move_id), amount in grouped.items():
            if self.currency_id.is_zero(amount):
                continue
            cmd.append((0, 0, {
                "partner_id": partner_id,
                "origin_move_id": move_id,
                "amount_base": abs(amount),
            }))
        self.line_ids = cmd
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_migrate(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("No hay saldos para migrar."))
        Advance = self.env["l10n_pe.advance"]
        created = self.env["l10n_pe.advance"]
        for line in self.line_ids.filtered(lambda l: l.to_migrate):
            created |= Advance.create({
                "advance_type": self.advance_type,
                "partner_id": line.partner_id.id,
                "currency_id": self.currency_id.id,
                "company_id": self.config_id.company_id.id,
                "date": line.origin_move_id.date or fields.Date.context_today(self),
                "config_id": self.config_id.id,
                "control_account_id": self.control_account_id.id,
                "origin_move_id": line.origin_move_id.id,
                "amount_base": line.amount_base,
                "amount_total": line.amount_base * 1.18,
                "amount_tax": line.amount_base * 0.18,
                "note": _("Migracion de saldo inicial."),
            })
        return {
            "type": "ir.actions.act_window",
            "name": _("Documentos migrados"),
            "res_model": "l10n_pe.advance",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
        }


class L10nPeAdvanceMigrationWizardLine(models.TransientModel):
    _name = "l10n_pe.advance.migration.wizard.line"
    _description = "Linea de migracion de saldos"

    wizard_id = fields.Many2one(
        "l10n_pe.advance.migration.wizard", required=True, ondelete="cascade",
    )
    to_migrate = fields.Boolean(string="Migrar", default=True)
    partner_id = fields.Many2one("res.partner", string="Socio", required=True)
    origin_move_id = fields.Many2one("account.move", string="Asiento origen")
    currency_id = fields.Many2one(
        related="wizard_id.currency_id", string="Moneda",
    )
    amount_base = fields.Monetary(
        string="Saldo base", currency_field="currency_id",
    )
