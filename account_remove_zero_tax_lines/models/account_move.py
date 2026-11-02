# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools import float_is_zero


class AccountMove(models.Model):
    _inherit = 'account.move'

    has_zero_tax_lines = fields.Boolean(
        string='Tiene líneas de impuesto en cero',
        compute='_compute_has_zero_tax_lines',
    )

    @api.depends('line_ids.display_type', 'line_ids.debit', 'line_ids.credit')
    def _compute_has_zero_tax_lines(self):
        for move in self:
            move.has_zero_tax_lines = bool(move._get_zero_tax_lines())

    def _get_zero_tax_lines(self):
        """Devuelve las líneas display_type='tax' con debit=0 y credit=0."""
        self.ensure_one()
        rounding = (self.currency_id or self.company_id.currency_id).rounding
        return self.line_ids.filtered(
            lambda l: l.display_type == 'tax'
            and float_is_zero(l.debit, precision_rounding=rounding)
            and float_is_zero(l.credit, precision_rounding=rounding)
        )

    def _post(self, soft=True):
        for move in self:
            zero_lines = move._get_zero_tax_lines()
            if zero_lines:
                accounts = ', '.join(zero_lines.mapped('account_id.code'))
                move.message_post(body=_(
                    'Se eliminaron %(n)s línea(s) de impuesto con importe cero al confirmar: %(accounts)s',
                    n=len(zero_lines),
                    accounts=accounts,
                ))
                zero_lines.with_context(dynamic_unlink=True, check_move_validity=False).unlink()
        return super()._post(soft=soft)
