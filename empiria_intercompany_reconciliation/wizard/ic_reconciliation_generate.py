from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class IcReconciliationGenerate(models.TransientModel):
    _name = 'ic.reconciliation.generate'
    _description = 'Generar conciliación intercompany'

    period = fields.Selection(
        selection=[('all', 'Sin fecha desde (todo el historial)'), ('current_year', 'Año en curso'),
                   ('current_month', 'Mes en curso'), ('last_12', 'Últimos 12 meses'), ('year', 'Otro año'),
                   ('range', 'Desde - hasta')],
        string='Periodo', required=True, default='current_year',
        help='El emparejamiento usa siempre todo el historial hasta la fecha de corte. La fecha desde solo decide '
             'qué líneas se muestran y cuentan como pendientes; las partidas anteriores que siguen pendientes se '
             'resumen en "Arrastre anterior al periodo" (una línea por par y bloque).')
    year = fields.Selection(selection='_year_selection', string='Año',
                            default=lambda self: str(fields.Date.context_today(self).year))
    date_from = fields.Date(string='Desde')
    date_to = fields.Date(string='Hasta (fecha de corte)', required=True, default=fields.Date.context_today,
                          help='El saldo de cada par es el acumulado hasta ese día.')
    company_ids = fields.Many2many(
        'res.company', string='Empresas',
        default=lambda self: self.env['ic.reconciliation.config'].get_config().company_ids,
        help='Todas las de la configuración o solo un par (p.ej. JE-AL y Connected) para revisarlo rápido.')
    available_company_ids = fields.Many2many(
        'res.company', compute='_compute_available_company_ids')
    include_balanced = fields.Boolean(string='Incluir pares que cuadran',
                                      help='Para ver el grupo completo, también los pares sin diferencia.')

    @api.model
    def _year_selection(self):
        current = fields.Date.context_today(self).year
        return [(str(year), str(year)) for year in range(current, current - 8, -1)]

    def _compute_available_company_ids(self):
        companies = self.env['ic.reconciliation.config'].get_config().company_ids
        for wizard in self:
            wizard.available_company_ids = companies

    def _shortcut_dates(self):
        """(desde, hasta) de los atajos; None si el periodo se elige a mano."""
        today = fields.Date.context_today(self)
        if self.period == 'current_year':
            return date(today.year, 1, 1), today
        if self.period == 'current_month':
            return today.replace(day=1), today
        if self.period == 'last_12':
            return today + relativedelta(months=-12, days=1), today
        if self.period == 'year' and self.year:
            year = int(self.year)
            return date(year, 1, 1), min(date(year, 12, 31), today)
        return None

    @api.onchange('period', 'year')
    def _onchange_period(self):
        dates = self._shortcut_dates()
        if self.period == 'all':
            self.date_from = False
        elif dates:
            self.date_from, self.date_to = dates
        elif self.period == 'range' and not self.date_from:
            self.date_from = date(fields.Date.context_today(self).year, 1, 1)

    def _period_dates(self):
        self.ensure_one()
        if self.period == 'all':
            return False, self.date_to
        if self.period == 'year' and not self.year:
            raise UserError(_('Elija el año.'))
        dates = self._shortcut_dates()
        if dates:
            return dates
        if not self.date_from:
            raise UserError(_('Indique la fecha desde del periodo.'))
        if self.date_from > self.date_to:
            raise UserError(_('La fecha desde no puede ser posterior a la fecha hasta.'))
        return self.date_from, self.date_to

    def action_generate(self):
        self.ensure_one()
        date_from, date_to = self._period_dates()
        Run = self.env['ic.reconciliation.run']
        run = Run.create({
            'name': Run._run_name(date_from, date_to),
            'date_from': date_from,
            'date_to': date_to,
            'company_ids': [(6, 0, self.company_ids.ids)],
            'include_balanced': self.include_balanced,
            'origin': 'manual',
        })
        return run.action_compute()
