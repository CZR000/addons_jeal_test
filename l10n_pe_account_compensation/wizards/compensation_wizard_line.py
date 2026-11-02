# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CompensationWizardLine(models.TransientModel):
    _name = 'l10n_pe.compensation.wizard.line'
    _description = 'Línea del Wizard de Compensación'
    _order = 'invoice_date, id'

    wizard_id = fields.Many2one(
        comodel_name='l10n_pe.compensation.wizard',
        required=True,
        ondelete='cascade',
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura',
        required=True,
        readonly=True,
    )
    invoice_name = fields.Char(
        related='invoice_id.name',
        string='Número',
        readonly=True,
    )
    invoice_date = fields.Date(
        related='invoice_id.invoice_date',
        string='Fecha',
        readonly=True,
    )
    invoice_partner_id = fields.Many2one(
        related='invoice_id.partner_id',
        readonly=True,
    )
    invoice_move_type = fields.Selection(
        related='invoice_id.move_type',
        readonly=True,
    )
    invoice_rate = fields.Float(
        string='TC original',
        digits=(12, 6),
        help='Informativo. Los importes en moneda local se calculan por '
             'proporción exacta contra la línea AR/AP de la factura.',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda',
    )
    company_currency_id = fields.Many2one(
        related='wizard_id.company_currency_id',
        readonly=True,
    )
    amount_residual = fields.Monetary(
        string='Saldo pendiente',
        currency_field='currency_id',
    )
    # Residual en moneda local, tomado exactamente de la línea AR/AP de la
    # factura. Sirve para valorizar la línea del asiento sin recalcular por
    # TC y evitar AED automático al reconciliar.
    amount_residual_local = fields.Monetary(
        string='Saldo pendiente (local)',
        currency_field='company_currency_id',
    )
    amount_to_compensate = fields.Monetary(
        string='A compensar',
        currency_field='currency_id',
        default=0.0,
    )
    selected = fields.Boolean(
        string='Seleccionado',
        default=False,
    )

    @api.onchange('selected')
    def _onchange_selected(self):
        for line in self:
            if not line.selected:
                line.amount_to_compensate = 0.0
                continue
            wizard = line.wizard_id
            if not wizard or not wizard.move_id:
                line.amount_to_compensate = line.amount_residual
                continue
            other_selected_total = sum(
                other.amount_to_compensate
                for other in wizard.line_ids
                if other.selected and other.id != line.id and other != line
            )
            origin_available = wizard.move_id.amount_residual - other_selected_total
            if origin_available < 0:
                origin_available = 0.0
            line.amount_to_compensate = min(line.amount_residual, origin_available)