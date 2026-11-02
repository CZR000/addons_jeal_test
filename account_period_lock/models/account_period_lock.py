from odoo import api, fields, models, _
from odoo.exceptions import UserError

MONTHS_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre',
}


class AccountPeriodLock(models.Model):
    _name = 'account.period.lock'
    _description = 'Periodo de Bloqueo Contable'
    _order = 'date_start asc'
    _rec_name = 'name'

    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company,
    )
    name = fields.Char(string='Periodo', compute='_compute_name', store=True)
    date_start = fields.Date(string='Fecha Inicio', required=True)
    date_end = fields.Date(string='Fecha Fin', required=True)
    is_locked = fields.Boolean(string='Bloqueado', default=False)
    state = fields.Selection([
        ('open', 'Abierto'),
        ('locked', 'Bloqueado'),
    ], string='Estado', compute='_compute_state', store=True)

    _sql_constraints = [
        ('unique_period', 'UNIQUE(company_id, date_start, date_end)',
         'Ya existe un periodo con las mismas fechas para esta empresa.'),
    ]

    @api.depends('date_start')
    def _compute_name(self):
        for rec in self:
            if rec.date_start:
                rec.name = '%s %s' % (
                    MONTHS_ES.get(rec.date_start.month, ''),
                    rec.date_start.year,
                )
            else:
                rec.name = ''

    @api.depends('is_locked')
    def _compute_state(self):
        for rec in self:
            rec.state = 'locked' if rec.is_locked else 'open'

    def action_lock(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Solo los Administradores de Contabilidad pueden bloquear periodos.'))
        self.write({'is_locked': True})
        return self._reload_wizard()

    def action_unlock(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Solo los Administradores de Contabilidad pueden abrir periodos.'))
        self.write({'is_locked': False})
        return self._reload_wizard()

    def action_delete_period(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Solo los Administradores de Contabilidad pueden eliminar periodos.'))
        if self.is_locked:
            raise UserError(_('No se puede eliminar un periodo bloqueado. Ábralo primero.'))
        company = self.company_id
        self.unlink()
        return self._reload_wizard(company=company)

    def _reload_wizard(self, company=None):
        if company is None:
            company = self.env.company

        current_periods = self.env['account.period.lock'].search([
            ('company_id', '=', company.id),
        ])

        wizard_id = self.env.context.get('wizard_id')
        wizard = None

        if wizard_id:
            candidate = self.env['account.change.lock.date'].browse(wizard_id)
            if candidate.exists():
                wizard = candidate

        if wizard is not None:
            wizard.write({'period_lock_ids': [(6, 0, current_periods.ids)]})
        else:
            wizard = self.env['account.change.lock.date'].create({
                'period_lock_ids': [(6, 0, current_periods.ids)],
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.change.lock.date',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
            'views': [(False, 'form')],
        }
