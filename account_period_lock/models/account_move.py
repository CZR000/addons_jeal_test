from odoo import models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _check_period_lock(self, date=None):
        company = self.env.company
        locked_periods = company.period_lock_ids.filtered(lambda p: p.is_locked)
        if not locked_periods:
            return
        for move in self:
            check_date = date or move.date
            if not check_date:
                continue
            for period in locked_periods:
                if period.date_start <= check_date <= period.date_end:
                    raise UserError(_(
                        'No se puede modificar el asiento "%s" (fecha: %s) porque cae '
                        'dentro del periodo bloqueado "%s" (%s → %s).\n'
                        'Contacte al Administrador de Contabilidad para desbloquear el periodo.',
                        move.name or '/', check_date,
                        period.name, period.date_start, period.date_end,
                    ))

    def write(self, vals):
        if 'date' in vals:
            new_date = vals['date']
            for move in self.filtered(lambda m: m.state == 'posted'):
                self._check_period_lock(date=new_date)
        return super().write(vals)

    def action_post(self):
        self._check_period_lock()
        return super().action_post()

    def button_draft(self):
        self._check_period_lock()
        return super().button_draft()
