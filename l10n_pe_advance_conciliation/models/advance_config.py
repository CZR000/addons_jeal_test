# -*- coding: utf-8 -*-
from odoo import api, fields, models


class L10nPeAdvanceConfig(models.Model):
    _name = "l10n_pe.advance.config"
    _description = "Configuracion de anticipos y revolventes"

    advance_type = fields.Selection(
        selection=[
            ("customer", "Anticipo de cliente"),
            ("supplier", "Anticipo a proveedor"),
            ("revolving", "Revolvente"),
        ],
        string="Tipo",
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency", string="Moneda", required=True,
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        "res.company", string="Compania", required=True,
        default=lambda self: self.env.company,
    )
    control_account_id = fields.Many2one(
        "account.account", string="Cuenta de control", required=True,
        help="1220001 / 4220001 / 4512003. Debe permitir conciliacion y no "
             "tener una moneda forzada.",
    )
    origin_product_id = fields.Many2one(
        "product.product", string="Producto de origen",
        help="Producto que crea el anticipo al publicar la factura.",
    )
    application_product_id = fields.Many2one(
        "product.product", string="Producto de aplicacion",
        help="Opcional. Producto de la linea negativa que descuenta el "
             "anticipo. Si se deja vacio se usa el producto de origen.",
    )
    compensation_journal_id = fields.Many2one(
        "account.journal", string="Diario de compensacion",
        help="Diario donde se genera el asiento de compensacion del revolvente.",
    )
    revolving_journal_ids = fields.Many2many(
        "account.journal",
        "l10n_pe_advance_config_journal_rel",
        "config_id", "journal_id",
        string="Diarios que crean revolvente",
        help="Solo los apuntes al haber en estos diarios crean un revolvente. "
             "Si se deja vacio, cualquier diario lo dispara (no recomendado).",
    )
    closing_tolerance = fields.Float(
        string="Tolerancia de cierre", default=1.0,
        help="Saldo maximo que puede cerrarse por redondeo.",
    )
    rounding_expense_account_id = fields.Many2one(
        "account.account", string="Cuenta gasto por redondeo",
        help="6593004 Gasto por redondeo.",
    )
    rounding_income_account_id = fields.Many2one(
        "account.account", string="Cuenta ingreso por redondeo",
        help="7599001 Ingreso por redondeo.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "type_currency_company_uniq",
            "unique(advance_type, currency_id, company_id)",
            "Ya existe una configuracion para este tipo, moneda y compania.",
        ),
    ]

    @api.depends("advance_type", "currency_id")
    def _compute_display_name(self):
        labels = dict(self._fields["advance_type"].selection)
        for rec in self:
            rec.display_name = "%s - %s" % (
                labels.get(rec.advance_type, ""),
                rec.currency_id.name or "",
            )

    @api.model
    def _get_config(self, advance_type, control_account=None, currency=None, company=None):
        """Devuelve la configuracion que aplica, o un recordset vacio."""
        company = company or self.env.company
        domain = [("advance_type", "=", advance_type), ("company_id", "=", company.id)]
        if control_account:
            domain.append(("control_account_id", "=", control_account.id))
        if currency:
            domain.append(("currency_id", "=", currency.id))
        return self.search(domain, limit=1)
