# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class L10nPeAdvanceReconcileReport(models.Model):
    """Cuadre del modulo contra el mayor de la cuenta de control.

    Compara, por socio y cuenta de control:
      - Saldo del modulo: suma de amount_residual de los documentos abiertos.
      - Saldo contable: suma del residual por conciliar (amount_residual_currency)
        de los apuntes publicados en esa cuenta.
    La diferencia debe ser cero. Si no, hay movimientos hechos por fuera del flujo.
    """
    _name = "l10n_pe.advance.reconcile.report"
    _description = "Cuadre modulo vs contabilidad"
    _auto = False
    _rec_name = "partner_id"

    partner_id = fields.Many2one("res.partner", string="Socio", readonly=True)
    account_id = fields.Many2one(
        "account.account", string="Cuenta", readonly=True,
    )
    company_id = fields.Many2one("res.company", string="Compania", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True)
    module_balance = fields.Monetary(
        string="Saldo del modulo", currency_field="currency_id", readonly=True,
    )
    ledger_balance = fields.Monetary(
        string="Saldo contable (mayor)", currency_field="currency_id",
        readonly=True,
    )
    difference = fields.Monetary(
        string="Diferencia", currency_field="currency_id", readonly=True,
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                WITH control_accounts AS (
                    SELECT DISTINCT control_account_id AS account_id
                    FROM l10n_pe_advance
                    WHERE control_account_id IS NOT NULL
                ),
                module AS (
                    SELECT
                        a.partner_id,
                        a.control_account_id AS account_id,
                        a.company_id,
                        a.currency_id,
                        SUM(a.amount_residual) AS module_balance
                    FROM l10n_pe_advance a
                    WHERE a.state IN ('open', 'partial')
                    GROUP BY a.partner_id, a.control_account_id,
                             a.company_id, a.currency_id
                ),
                ledger AS (
                    SELECT
                        aml.partner_id,
                        aml.account_id,
                        aml.company_id,
                        SUM(ABS(COALESCE(aml.amount_residual_currency, 0.0)))
                            AS ledger_balance
                    FROM account_move_line aml
                    JOIN account_move am ON am.id = aml.move_id
                    JOIN control_accounts ca ON ca.account_id = aml.account_id
                    WHERE am.state = 'posted'
                    GROUP BY aml.partner_id, aml.account_id, aml.company_id
                )
                SELECT
                    row_number() OVER () AS id,
                    COALESCE(m.partner_id, l.partner_id) AS partner_id,
                    COALESCE(m.account_id, l.account_id) AS account_id,
                    COALESCE(m.company_id, l.company_id) AS company_id,
                    m.currency_id AS currency_id,
                    COALESCE(m.module_balance, 0.0) AS module_balance,
                    COALESCE(l.ledger_balance, 0.0) AS ledger_balance,
                    COALESCE(l.ledger_balance, 0.0)
                        - COALESCE(m.module_balance, 0.0) AS difference
                FROM module m
                FULL OUTER JOIN ledger l
                    ON  m.partner_id = l.partner_id
                    AND m.account_id = l.account_id
                    AND m.company_id = l.company_id
            )
            """
            % self._table
        )
