# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        self._check_analytic_account_restrictions()
        return super()._post(soft=soft)

    def _check_analytic_account_restrictions(self):
        errors = []
        for move in self:
            for line in move.line_ids.filtered(
                lambda l: l.analytic_distribution and l.display_type not in ('line_section', 'line_note')
            ):
                errors += line._get_analytic_restriction_errors(move.name or move.ref or _('Nuevo'))
        if errors:
            raise UserError('\n\n'.join(errors))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.constrains('analytic_distribution', 'account_id')
    def _check_analytic_restriction_on_save(self):
        errors = []
        for line in self.filtered(
            lambda l: l.analytic_distribution and l.display_type not in ('line_section', 'line_note')
        ):
            move_ref = line.move_id.name or line.move_id.ref or _('Nuevo')
            errors += line._get_analytic_restriction_errors(move_ref)
        if errors:
            raise UserError('\n\n'.join(errors))

    def _get_analytic_restriction_errors(self, move_ref):
        self.ensure_one()
        errors = []
        # In Odoo 18, analytic_distribution keys can be composite "123,456"
        # (multiple analytic accounts across plans sharing the same percentage).
        analytic_ids = [
            int(aid)
            for key in (self.analytic_distribution or {})
            for aid in key.split(',')
            if aid.isdigit()
        ]
        for analytic in self.env['account.analytic.account'].browse(analytic_ids):
            if not analytic.allowed_account_ids:
                continue
            if self.account_id not in analytic.allowed_account_ids:
                errors.append(
                    _("Asiento «%(move)s» - Línea con cuenta «%(account)s»: "
                      "la cuenta analítica «%(analytic)s» no está permitida "
                      "para esta cuenta contable. Cuentas permitidas: %(allowed)s.",
                      move=move_ref,
                      account=self.account_id.display_name,
                      analytic=analytic.display_name,
                      allowed=', '.join(analytic.allowed_account_ids.mapped('display_name')),
                      )
                )
        return errors
