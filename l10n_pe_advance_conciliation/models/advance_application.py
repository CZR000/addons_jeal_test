# -*- coding: utf-8 -*-
from odoo import fields, models


class L10nPeAdvanceApplication(models.Model):
    _name = "l10n_pe.advance.application"
    _description = "Aplicacion de anticipo / revolvente"
    _order = "date, id"

    advance_id = fields.Many2one(
        "l10n_pe.advance", string="Documento", required=True,
        ondelete="cascade", index=True,
    )
    advance_type = fields.Selection(
        related="advance_id.advance_type", store=True, string="Tipo",
    )
    partner_id = fields.Many2one(
        related="advance_id.partner_id", store=True, string="Socio",
    )
    currency_id = fields.Many2one(
        related="advance_id.currency_id", store=True, string="Moneda",
    )
    company_id = fields.Many2one(
        related="advance_id.company_id", store=True, string="Compania",
    )
    move_id = fields.Many2one(
        "account.move", string="Factura / asiento destino", index=True,
    )
    invoice_id = fields.Many2one(
        "account.move", string="Factura aplicada", index=True,
        help="Factura en la que se uso el anticipo o el revolvente. En las "
             "facturas coincide con el asiento destino; en el revolvente es "
             "la factura compensada por el asiento de compensacion.",
    )
    move_line_id = fields.Many2one(
        "account.move.line", string="Apunte en cuenta de control",
    )
    date = fields.Date(string="Fecha", default=fields.Date.context_today)
    application_type = fields.Selection(
        selection=[
            ("invoice", "Factura"),
            ("credit_note", "Nota de credito"),
            ("compensation", "Compensacion"),
            ("rounding", "Redondeo"),
        ],
        string="Tipo de movimiento", default="invoice",
    )
    amount_base = fields.Monetary(
        string="Monto base", currency_field="currency_id",
    )
    amount_total = fields.Monetary(
        string="Monto con IGV", currency_field="currency_id",
    )
    amount_company_currency = fields.Monetary(
        string="Equivalente compania", currency_field="company_currency_id",
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id", string="Moneda compania",
    )
    full_reconcile_id = fields.Many2one(
        "account.full.reconcile", string="Conciliacion",
    )
    reconcile_state = fields.Char(
        string="Conciliacion 122", compute="_compute_reconcile_state",
    )
    move_state = fields.Selection(
        related="move_id.state", store=True, string="Estado asiento",
    )
    active = fields.Boolean(default=True)

    def _compute_reconcile_state(self):
        for rec in self:
            if rec.full_reconcile_id:
                rec.reconcile_state = "Conciliado automaticamente"
            elif rec.move_line_id and rec.move_line_id.reconciled:
                rec.reconcile_state = "Conciliado"
            elif rec.move_line_id and rec.move_line_id.matched_debit_ids:
                rec.reconcile_state = "Parcial"
            else:
                rec.reconcile_state = "Pendiente"
