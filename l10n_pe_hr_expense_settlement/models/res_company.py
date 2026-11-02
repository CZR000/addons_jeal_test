from odoo import fields, models

# Cuentas por cobrar al personal (entregas a rendir) cuando la compañía no
# configura las suyas: mismo criterio que la pestaña informativa de
# je_approval_expense_flow.
DEFAULT_ADVANCE_ACCOUNT_PREFIX = '14'


class ResCompany(models.Model):
    _inherit = 'res.company'

    hr_expense_settlement_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de liquidación de rendiciones',
        check_company=True,
        domain="[('type', '=', 'general')]",
        help='Diario misceláneo donde se registra el asiento que cancela la factura '
             'del proveedor contra el anticipo del empleado (sin movimiento de caja).',
    )
    hr_expense_auto_settle = fields.Boolean(
        string='Liquidar automáticamente',
        default=True,
        help='Al publicar una factura que viene de un informe de gastos se liquida sola contra '
             'los anticipos del empleado (del más antiguo al más reciente); lo que no cubran '
             'queda como saldo a reembolsar al empleado.',
    )
    hr_expense_non_register_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de comprobantes fuera del Registro de Compras',
        check_company=True,
        domain="[('type', '=', 'purchase')]",
        help='Diario de compras (excluido del PLE) donde se registran los comprobantes '
             'de gastos marcados como "No va al Registro de Compras".',
    )
    hr_expense_advance_account_ids = fields.Many2many(
        comodel_name='account.account',
        relation='res_company_hr_expense_advance_account_rel',
        column1='company_id',
        column2='account_id',
        string='Cuentas de entregas a rendir',
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
        help='Cuentas donde se registran los anticipos a los empleados (p.ej. 1413). '
             'Si se deja vacío se usan todas las cuentas conciliables que empiezan con 14.',
    )

    hr_expense_petty_cash_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta del fondo de caja chica',
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
        help='Cuenta donde se registra el fondo de caja chica entregado al empleado. '
             'Vacío: la cuenta de entregas a rendir de la moneda del fondo.',
    )
    hr_expense_block_pending_advances = fields.Boolean(
        string='Bloquear desembolsos con rendición pendiente',
        default=True,
        help='No se puede registrar una entrega a rendir, un fondo o una reposición de caja chica a un empleado '
             'que tiene otro desembolso sin rendir en cualquier empresa del grupo.',
    )
    hr_expense_block_pending_days = fields.Integer(
        string='Días de tolerancia',
        help='Solo bloquean los desembolsos pendientes con más de estos días. 0: bloqueo inmediato.',
    )
    hr_expense_block_include_petty_cash = fields.Boolean(
        string='El fondo de caja chica cuenta como pendiente',
        help='Si se marca, el saldo del fondo de caja chica del empleado también bloquea nuevos desembolsos '
             '(incluida su reposición). Si no, solo las entregas a rendir.',
    )
    hr_expense_petty_cash_settlement_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario de liquidación de caja chica',
        check_company=True,
        domain="[('type', '=', 'general')]",
        help='Diario de los asientos que liquidan las rendiciones del fondo de caja chica. '
             'Vacío: el diario de liquidación de rendiciones.',
    )

    def _get_hr_expense_advance_accounts(self):
        self.ensure_one()
        if self.hr_expense_advance_account_ids:
            return self.hr_expense_advance_account_ids
        # La cuenta propia de caja chica (p.ej. 1413002) no es una entrega a rendir.
        return self.env['account.account'].search([
            *self.env['account.account']._check_company_domain(self),
            ('code', '=like', f'{DEFAULT_ADVANCE_ACCOUNT_PREFIX}%'),
            ('reconcile', '=', True),
            ('id', '!=', self.hr_expense_petty_cash_account_id.id),
        ])

    def _get_hr_expense_employee_accounts(self):
        """Todas las cuentas donde el empleado puede tener anticipos abiertos."""
        self.ensure_one()
        return self._get_hr_expense_advance_accounts() | self.hr_expense_petty_cash_account_id

    def _get_hr_expense_advance_account(self, currency):
        """Cuenta de entregas a rendir de una moneda: la que exige esa moneda
        (p.ej. 1413001 en USD) o, si no hay, la que no exige moneda (1413000)."""
        self.ensure_one()
        accounts = self._get_hr_expense_advance_accounts()
        return (
            accounts.filtered(lambda account: account.currency_id == currency)[:1]
            or accounts.filtered(lambda account: not account.currency_id)[:1]
        )

    def _get_hr_expense_petty_cash_account(self, currency):
        self.ensure_one()
        account = self.hr_expense_petty_cash_account_id
        if account and account.currency_id in (currency, self.env['res.currency']):
            return account
        return self._get_hr_expense_advance_account(currency)
