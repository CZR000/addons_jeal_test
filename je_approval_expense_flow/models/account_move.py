from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def unlink(self):
        # account_move_protect.unlink() revisa el grupo "Eliminar asientos"
        # incondicionalmente, incluso sobre un recordset vacío. Odoo core llama
        # unlink() sobre conjuntos vacíos como parte normal de action_post()
        # (limpieza de "draft moves" de transacciones de pago no usadas) - eso
        # no debería requerir ningún permiso. Cortamos ese caso antes de que
        # account_move_protect (que corre después, más adentro del MRO, porque
        # este módulo lo declara como dependencia) llegue a validar el grupo.
        if not self:
            return True
        return super().unlink()

    # ------------------------------------------------------------------
    # Detalle del empleado en el asiento generado desde un Informe de Gastos:
    # cuenta 14 (cuentas por cobrar/pagar al personal) y pagos pendientes de
    # conciliar de ese mismo empleado, para facilitar el cruce al aprobador.
    #
    # OJO: "expense_sheet_id" ya existe de forma NATIVA en account.move - es
    # el inverse_name del One2many hr.expense.sheet.account_move_ids (ver
    # hr_expense/models/hr_expense_sheet.py). No hay que redefinirlo: crear
    # un campo propio con el mismo nombre pisa el campo real (store=True) con
    # uno computado no-almacenado y rompe esa relación nativa por completo.
    # ------------------------------------------------------------------
    expense_employee_partner_id = fields.Many2one(
        'res.partner',
        string='Contacto del empleado',
        compute='_compute_expense_employee_partner_id',
    )
    expense_employee_account14_line_ids = fields.Many2many(
        'account.move.line',
        string='Cuenta 14 pendiente del empleado',
        compute='_compute_expense_employee_details',
    )
    expense_employee_pending_payment_ids = fields.Many2many(
        'account.payment',
        string='Pagos pendientes de conciliar del empleado',
        compute='_compute_expense_employee_details',
    )

    @api.depends('expense_sheet_id.employee_id')
    def _compute_expense_employee_partner_id(self):
        for move in self:
            employee = move.expense_sheet_id.employee_id
            move.expense_employee_partner_id = employee.sudo().work_contact_id if employee else False

    @api.depends('expense_employee_partner_id')
    def _compute_expense_employee_details(self):
        for move in self:
            partner = move.expense_employee_partner_id
            if not partner:
                move.expense_employee_account14_line_ids = False
                move.expense_employee_pending_payment_ids = False
                continue
            move.expense_employee_account14_line_ids = self.env['account.move.line'].sudo().search([
                ('partner_id', '=', partner.id),
                ('account_id.code', '=like', '14%'),
                ('reconciled', '=', False),
                ('move_id', '!=', move.id),
                ('parent_state', '=', 'posted'),
            ])
            # Solo pagos vigentes de la compañía de la factura: los cancelados o
            # rechazados no están pendientes de nada y se veían duplicados.
            move.expense_employee_pending_payment_ids = self.env['account.payment'].sudo().search([
                ('company_id', '=', move.company_id.id),
                ('partner_id', '=', partner.id),
                ('is_reconciled', '=', False),
                ('state', 'not in', ('draft', 'canceled', 'rejected')),
            ])
