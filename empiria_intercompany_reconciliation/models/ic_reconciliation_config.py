from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from ..engine import DEFAULT_PARAMS


class IcReconciliationConfig(models.Model):
    _name = 'ic.reconciliation.config'
    _description = 'Configuración de la conciliación intercompany'

    name = fields.Char(default='Conciliación intercompany', required=True)
    company_ids = fields.Many2many(
        comodel_name='res.company',
        relation='ic_reconciliation_config_company_rel',
        string='Empresas del grupo',
        help='Empresas que se concilian entre sí. Cada una se reconoce como socio por su RUC '
             '(también sus direcciones y almacenes con el mismo RUC). Vacío: todas las empresas con RUC.',
    )
    receivable_prefixes = fields.Char(
        string='Cuentas por cobrar', default='12,13,14,16,17,19',
        help='Prefijos de cuentas por cobrar (incluye anticipos 122). Con las por pagar de la otra empresa '
             'forman el bloque "A por cobrar / B por pagar".')
    payable_prefixes = fields.Char(
        string='Cuentas por pagar', default='41,42,43,44,45,46,47',
        help='Prefijos de cuentas por pagar (incluye anticipos 4220 y préstamos 46).')
    fx_journal_ids = fields.Many2many(
        comodel_name='account.journal',
        relation='ic_reconciliation_config_fx_journal_rel',
        string='Diarios de diferencia de cambio',
        help='Regla 2: sus asientos se clasifican como diferencia de cambio sin detalle por documento. '
             'Vacío: el diario de diferencia de cambio de cada empresa.',
    )
    amount_tolerance = fields.Float(string='Tolerancia de importe', default=DEFAULT_PARAMS['amount_tolerance'])
    rounding_tolerance = fields.Float(string='Tolerancia de redondeo', default=DEFAULT_PARAMS['rounding_tolerance'])
    number_days = fields.Integer(string='Días número distinto', default=DEFAULT_PARAMS['number_days'])
    payment_days = fields.Integer(string='Días pago ↔ cobro', default=DEFAULT_PARAMS['payment_days'])
    grouped_days = fields.Integer(string='Días pagos agrupados', default=DEFAULT_PARAMS['grouped_days'])
    triangular_days = fields.Integer(string='Días compensación 3 empresas', default=DEFAULT_PARAMS['triangular_days'])
    other_currency_percent = fields.Float(string='Otra moneda: % de tolerancia', default=DEFAULT_PARAMS['other_currency_percent'])
    other_currency_minimum = fields.Float(string='Otra moneda: mínimo S/', default=DEFAULT_PARAMS['other_currency_minimum'])
    rate_diff_percent = fields.Float(
        string='Tipo de cambio distinto: % de tolerancia', default=DEFAULT_PARAMS['rate_diff_percent'],
        help='Comprobante con el mismo importe en su moneda y distinto en soles: si la diferencia no supera este '
             'porcentaje del importe en soles (o el mínimo), queda como redondeo y no como pendiente.')
    rate_diff_minimum = fields.Float(string='Tipo de cambio distinto: mínimo S/',
                                     default=DEFAULT_PARAMS['rate_diff_minimum'])
    combination_tolerance = fields.Float(
        string='Tolerancia de agrupaciones', default=DEFAULT_PARAMS['combination_tolerance'],
        help='Reglas 16 a 18 (pago más retención, un pago contra varios, anticipos en varias partes): '
             'diferencia máxima en soles entre las sumas.')
    suggestion_percent = fields.Float(
        string='Sugerencias: % de diferencia', default=DEFAULT_PARAMS['suggestion_percent'],
        help='Se sugiere como posible contraparte una partida pendiente de la otra empresa cuyo monto difiere '
             'hasta este porcentaje (no se empareja sola).')
    suggestion_days = fields.Integer(string='Sugerencias: días', default=DEFAULT_PARAMS['suggestion_days'])
    company_keywords = fields.Text(
        string='Alias de empresas en glosas',
        help='Regla 13 (compensación de 3 empresas): palabras con que las glosas mencionan a una empresa, '
             'una línea por empresa con el formato "RUC: palabra1, palabra2". La razón social ya se usa.',
    )
    responsible_user_id = fields.Many2one(
        comodel_name='res.users', string='Responsable',
        help='Recibe el aviso de la ejecución diaria si hay pendientes nuevos o el control de algún par no es 0.')
    cron_period = fields.Selection(
        selection=[('all', 'Sin límite'), ('current_year', 'Año en curso'), ('months', 'Últimos N meses'),
                   ('fixed', 'Desde una fecha fija')],
        string='Periodo de la ejecución diaria', required=True, default='current_year',
        help='Fecha desde de las corridas automáticas; la fecha de corte es siempre el día de la corrida.')
    cron_months = fields.Integer(string='Meses', default=12)
    cron_date_from = fields.Date(string='Desde')
    keep_runs = fields.Integer(
        string='Ejecuciones a conservar', default=30,
        help='Ejecuciones automáticas que se conservan; las de cierre de mes se conservan siempre.')

    @api.constrains('receivable_prefixes', 'payable_prefixes', 'cron_period', 'cron_months', 'cron_date_from')
    def _check_prefixes(self):
        for config in self:
            receivable = set(config._prefixes('receivable'))
            payable = set(config._prefixes('payable'))
            if receivable & payable:
                raise ValidationError(_('Un prefijo no puede ser por cobrar y por pagar a la vez: %s',
                                        ', '.join(sorted(receivable & payable))))
            if any(not prefix.isdigit() for prefix in receivable | payable):
                raise ValidationError(_('Los prefijos de cuentas deben ser números separados por comas.'))
            if config.cron_period == 'months' and config.cron_months < 1:
                raise ValidationError(_('Indique cuántos meses toma la ejecución diaria.'))
            if config.cron_period == 'fixed' and not config.cron_date_from:
                raise ValidationError(_('Indique la fecha desde de la ejecución diaria.'))

    @api.model
    def get_config(self):
        config = self.sudo().search([], limit=1)
        if not config:
            config = self.sudo().create({})
        return config

    def _split(self, value):
        return [part.strip() for part in (value or '').split(',') if part.strip()]

    def _prefixes(self, kind):
        """Prefijos 'receivable' o 'payable'."""
        self.ensure_one()
        return self._split(self[f'{kind}_prefixes'])

    def _get_companies(self):
        """Empresas elegidas o, si no hay ninguna, todas las que tienen RUC (sin RUC
        no se las puede reconocer como socio)."""
        self.ensure_one()
        return self.company_ids or self.env['res.company'].sudo().search([('vat', '!=', False)])

    def _cron_date_from(self, today):
        self.ensure_one()
        if self.cron_period == 'current_year':
            return date(today.year, 1, 1)
        if self.cron_period == 'months':
            return today + relativedelta(months=-self.cron_months, days=1)
        if self.cron_period == 'fixed':
            return self.cron_date_from
        return False

    def _engine_params(self):
        self.ensure_one()
        return {field: self[field] for field in DEFAULT_PARAMS if field in self._fields}

    def _keywords_by_company(self):
        """{company_id: [palabras]} a partir de "RUC: palabra1, palabra2"."""
        self.ensure_one()
        by_vat = {company.vat: company.id for company in self.company_ids if company.vat}
        result = {}
        for raw in (self.company_keywords or '').splitlines():
            vat, _sep, words = raw.partition(':')
            company_id = by_vat.get(vat.strip())
            if company_id:
                result.setdefault(company_id, []).extend(self._split(words))
        return result

    def action_open(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.get_config().id,
            'view_mode': 'form',
            'target': 'current',
        }
