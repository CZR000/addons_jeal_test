from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountChangeLockDate(models.TransientModel):
    _inherit = 'account.change.lock.date'

    period_lock_ids = fields.Many2many(
        'account.period.lock',
        string='Periodos de Bloqueo',
    )
    new_date_start = fields.Date(string='Fecha Inicio')
    new_date_end = fields.Date(string='Fecha Fin')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'period_lock_ids' in fields_list:
            periods = self.env['account.period.lock'].search([
                ('company_id', '=', self.env.company.id),
            ])
            res['period_lock_ids'] = [(6, 0, periods.ids)]
        return res

    def action_add_period(self):
        if not self.env.user.has_groups('account.group_account_manager'):
            raise UserError(_('Solo los Administradores de Contabilidad pueden agregar periodos.'))
        if not self.new_date_start or not self.new_date_end:
            raise UserError(_('Debe ingresar la Fecha Inicio y Fecha Fin del nuevo periodo.'))
        if self.new_date_start > self.new_date_end:
            raise UserError(_('La fecha de inicio no puede ser mayor que la fecha fin.'))
        self.env['account.period.lock'].create({
            'company_id': self.env.company.id,
            'date_start': self.new_date_start,
            'date_end': self.new_date_end,
        })
        all_periods = self.env['account.period.lock'].search([
            ('company_id', '=', self.env.company.id),
        ])
        self.write({
            'period_lock_ids': [(6, 0, all_periods.ids)],
            'new_date_start': False,
            'new_date_end': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'views': [(False, 'form')],
        }
