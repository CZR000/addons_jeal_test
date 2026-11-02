# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nPeAdvanceStatementWizard(models.TransientModel):
    """Filtro del estado de cuenta por socio: agrupa todos los documentos
    (ANTC o REV) del socio, del tipo y la moneda elegidos, en un rango de
    fechas, con saldo inicial, movimientos y saldo acumulado."""
    _name = "l10n_pe.advance.statement.wizard"
    _description = "Estado de cuenta de anticipos/revolventes por socio"

    company_id = fields.Many2one(
        "res.company", string="Compania", required=True,
        default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one(
        "res.partner", string="Socio", required=True,
    )
    advance_type = fields.Selection(
        selection=[
            ("customer", "Anticipo de cliente"),
            ("supplier", "Anticipo a proveedor"),
            ("revolving", "Revolvente"),
        ],
        string="Tipo", required=True, default="revolving",
    )
    currency_id = fields.Many2one(
        "res.currency", string="Moneda",
        help="Vacio: todas las monedas (un bloque por documento, cada uno en "
             "su moneda).",
    )
    date_from = fields.Date(string="Desde")
    date_to = fields.Date(
        string="Hasta", required=True, default=fields.Date.context_today,
    )
    only_with_balance = fields.Boolean(
        string="Solo documentos con saldo o movimientos en el rango",
        default=True,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wiz in self:
            if wiz.date_from and wiz.date_to and wiz.date_from > wiz.date_to:
                raise UserError(_("La fecha Desde no puede ser mayor que Hasta."))

    def _get_advances(self):
        self.ensure_one()
        domain = [
            ("partner_id", "=", self.partner_id.commercial_partner_id.id),
            ("advance_type", "=", self.advance_type),
            ("company_id", "=", self.company_id.id),
            ("date", "<=", self.date_to),
        ]
        if self.currency_id:
            domain.append(("currency_id", "=", self.currency_id.id))
        return self.env["l10n_pe.advance"].search(domain, order="date, id")

    def action_print(self):
        self.ensure_one()
        advances = self._get_advances()
        if not advances:
            raise UserError(
                _("El socio no tiene documentos de ese tipo hasta la fecha "
                  "indicada.")
            )
        data = {
            "partner_id": self.partner_id.commercial_partner_id.id,
            "advance_type": self.advance_type,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id or False,
            "date_from": fields.Date.to_string(self.date_from) if self.date_from else False,
            "date_to": fields.Date.to_string(self.date_to),
            "only_with_balance": self.only_with_balance,
            "advance_ids": advances.ids,
        }
        return self.env.ref(
            "l10n_pe_advance_conciliation.action_report_advance_partner"
        ).report_action(advances, data=data)


class ReportAdvanceStatementPartner(models.AbstractModel):
    _name = "report.l10n_pe_advance_conciliation.report_advance_partner"
    _description = "Estado de cuenta por socio (anticipos/revolventes)"

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        Advance = self.env["l10n_pe.advance"]
        advances = Advance.browse(data.get("advance_ids") or docids).exists()
        date_from = data.get("date_from") or False
        date_to = data.get("date_to") or False
        blocks = []
        totals = {}
        for adv in advances:
            st = adv._l10n_pe_statement_rows(date_from, date_to)
            if data.get("only_with_balance", True) and not st["rows"] and \
                    adv.currency_id.is_zero(st["closing"]):
                continue
            blocks.append({"doc": adv, "st": st})
            cur = adv.currency_id
            tot = totals.setdefault(cur.id, {
                "currency": cur, "opening": 0.0, "income": 0.0,
                "applied": 0.0, "closing": 0.0,
            })
            for key in ("opening", "income", "applied", "closing"):
                tot[key] += st[key]
        types = dict(Advance._fields["advance_type"].selection)
        return {
            "doc_ids": advances.ids,
            "doc_model": "l10n_pe.advance",
            "docs": advances,
            "blocks": blocks,
            "totals": list(totals.values()),
            "partner": self.env["res.partner"].browse(data.get("partner_id")),
            "type_label": types.get(data.get("advance_type"), ""),
            "company": self.env["res.company"].browse(
                data.get("company_id") or self.env.company.id
            ),
            "date_from": fields.Date.to_date(date_from) if date_from else False,
            "date_to": fields.Date.to_date(date_to) if date_to else False,
        }
