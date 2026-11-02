from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    hr_expense_settlement_bill_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura rendida',
        readonly=True,
        copy=False,
        index='btree_not_null',
        help='Factura de proveedor que este asiento liquida contra el anticipo del empleado.',
    )
    hr_expense_settlement_move_ids = fields.One2many(
        comodel_name='account.move',
        inverse_name='hr_expense_settlement_bill_id',
        string='Liquidaciones de rendición',
    )
    hr_expense_settlement_count = fields.Integer(compute='_compute_hr_expense_settlement_count')
    hr_expense_can_settle = fields.Boolean(compute='_compute_hr_expense_can_settle')

    @api.depends('hr_expense_settlement_move_ids')
    def _compute_hr_expense_settlement_count(self):
        for move in self:
            move.hr_expense_settlement_count = len(move.hr_expense_settlement_move_ids)

    @api.depends('move_type', 'state', 'payment_state', 'expense_employee_partner_id')
    def _compute_hr_expense_can_settle(self):
        for move in self:
            move.hr_expense_can_settle = (
                move.move_type == 'in_invoice'
                and move.state == 'posted'
                and move.payment_state in ('not_paid', 'partial')
                and bool(move.expense_employee_partner_id)
            )

    @api.depends('expense_employee_partner_id')
    def _compute_expense_employee_details(self):
        # La pestaña informativa de je_approval_expense_flow y el botón
        # "Conciliar con Anticipo" deben mostrar exactamente los mismos anticipos.
        super()._compute_expense_employee_details()
        for move in self:
            move.expense_employee_account14_line_ids = move.sudo()._get_expense_employee_advance_lines()

    def _get_expense_employee_advance_lines(self):
        """Apuntes abiertos del empleado del informe en las cuentas de entregas a
        rendir de la compañía (deudores = anticipos por rendir, acreedores =
        saldos a reembolsarle)."""
        self.ensure_one()
        partner = self.expense_employee_partner_id
        if not partner:
            return self.env['account.move.line']
        return self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('partner_id', '=', partner.id),
            ('account_id', 'in', self.company_id._get_hr_expense_employee_accounts().ids),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('move_id', '!=', self._origin.id),
        ], order='date, id')

    def _post(self, soft=True):
        posted = super()._post(soft)
        posted._hr_expense_auto_settle()
        return posted

    def _hr_expense_auto_settle(self):
        """Liquida contra los anticipos del empleado las facturas de comprobantes
        rendidos, en la fecha contable de la factura. Si algo lo impide, la factura
        igual queda publicada: se deja constancia en el chatter y el botón
        "Conciliar con Anticipo" sigue disponible."""
        bills = self.filtered(lambda move: (
            move.hr_expense_can_settle
            and move.company_id.hr_expense_auto_settle
            and move.company_id.hr_expense_settlement_journal_id
        ))
        for bill in bills:
            try:
                with self.env.cr.savepoint():
                    self.env['hr.expense.settlement.wizard'].create({
                        'move_id': bill.id,
                        'date': bill.date,
                    }).action_confirm()
            except UserError as error:
                bill.message_post(body=_(
                    'No se pudo liquidar automáticamente contra los anticipos del empleado: %s',
                    error.args[0],
                ))

    def action_open_hr_expense_settlement_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Conciliar con Anticipo'),
            'res_model': 'hr.expense.settlement.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }

    def action_view_hr_expense_settlements(self):
        self.ensure_one()
        return self.hr_expense_settlement_move_ids._get_records_action(name=_('Liquidaciones de rendición'))
