from odoo import _, api, fields, models

_TYPE = [
    ('transport', 'Transporte'),
    ('process', 'Proceso'),
    ('billed', 'Facturado')
]


class CostLiquidation(models.Model):
    _name = 'account.liquidation.line'
    _description = 'Transporte de liquidación'
    _check_company_auto = True

    _sql_constraints = [
        ('unique_account_liquidation_line', 'UNIQUE(liquidation_id, type, move_id)', 'Un movimiento con este tipo ya esta en la liquidación.')
    ]

    liquidation_id = fields.Many2one(
        string='Liquidación',
        comodel_name='report.liquidation',
        required=True,
        ondelete='cascade'
    )
    type = fields.Selection(
        string='Tipo',
        selection=_TYPE,
        index=True,
        required=True,
    )
    move_id = fields.Many2one(
        string='Comprobante',
        comodel_name='account.move',
        check_company=True
    )
    company_id = fields.Many2one(
        string='Compania',
        comodel_name='res.company',
        related='liquidation_id.company_id',
        store=True
    )
    company_currency_id = fields.Many2one(
        string='Moneda compañia',
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True
    )
    move_currency_id = fields.Many2one(
        string='Moneda del comprobante',
        related='move_id.currency_id',
        store=True
    )
    exchange_rate = fields.Float(
        string='Tipo de cambio',
        digits=0,
        related='move_id.exchange_rate',
        store=True
    )
    partner_id = fields.Many2one(
        string='Proveedor',
        comodel_name='res.partner',
        related='move_id.partner_id',
        store=True
    )
    ref = fields.Char(
        string='Número',
        related='move_id.ref',
        store=True
    )
    invoice_date = fields.Date(
        string='Fecha factura',
        related='move_id.invoice_date',
        store=True
    )

    # MOVE AMOUNTS
    subtotal = fields.Monetary(
        string='Importe Base',
        related='move_id.amount_untaxed',
        store=True,
        readonly=True,
        currency_field='move_currency_id'
    )
    tax = fields.Monetary(
        related='move_id.amount_tax',
        store=True,
        readonly=True,
        currency_field='move_currency_id'
    )
    total = fields.Monetary(
        related='move_id.amount_total',
        store=True,
        readonly=True,
        currency_field='move_currency_id'
    )

    # AMOUNTS IN COMPANY CURRENCY
    subtotal_company = fields.Monetary(
        string='Subtotal',
        compute='_compute_company_amounts',
        store=True,
        currency_field='company_currency_id'
    )
    tax_company = fields.Monetary(
        string='IGV',
        compute='_compute_company_amounts',
        store=True,
        currency_field='company_currency_id'
    )
    total_company = fields.Monetary(
        string='Total en moneda de compañía',
        compute='_compute_company_amounts',
        store=True,
        currency_field='company_currency_id'
    )

    @api.depends('move_id', 'move_id.currency_id', 'move_id.invoice_date', 'company_currency_id', 'company_id')
    def _compute_company_amounts(self):
        for rec in self:
            if not rec.move_id:
                rec.subtotal_company = rec.tax_company = rec.total_company = 0.0
                continue
            date = rec.move_id.invoice_date or rec.move_id.date or fields.Date.context_today(rec)
            from_cur = rec.move_id.currency_id
            to_cur = rec.company_currency_id
            company = rec.company_id
            rec.subtotal_company = from_cur._convert(rec.move_id.amount_untaxed, to_cur, company, date)
            rec.tax_company = from_cur._convert(rec.move_id.amount_tax, to_cur, company, date)
            rec.total_company = from_cur._convert(rec.move_id.amount_total, to_cur, company, date)
