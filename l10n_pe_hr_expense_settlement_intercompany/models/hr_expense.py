import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _vat_digits(vat):
    return re.sub(r'\D', '', vat or '')


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    # La empresa se elige por su contacto: el empleado no tiene acceso a las otras
    # compañías (regla estándar de res.company), los contactos sí son compartidos.
    l10n_pe_charged_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Empresa que asume el gasto',
        compute='_compute_l10n_pe_charged_partner_id', store=True, readonly=False,
        domain="[('id', 'in', l10n_pe_ic_allowed_partner_ids)]",
        help='Empresa del grupo a la que se emitió el comprobante. Si no es la del informe, aquí no se '
             'registra factura: queda una cuenta por cobrar a esa empresa y allá se crea la factura en borrador.',
    )
    l10n_pe_ic_allowed_partner_ids = fields.Many2many(
        comodel_name='res.partner',
        compute='_compute_l10n_pe_ic_allowed_partner_ids',
    )
    l10n_pe_is_intercompany = fields.Boolean(
        string='Gasto de otra empresa',
        compute='_compute_l10n_pe_is_intercompany', store=True,
    )
    l10n_pe_ic_customer_vat = fields.Char(
        string='RUC del adquiriente',
        compute='_compute_l10n_pe_ic_customer_vat', store=True, readonly=False,
        help='RUC del cliente que figura en el comprobante. Se completa con el de la empresa que asume el gasto; '
             'puede cambiarse si el comprobante se emitió a otro RUC (se advierte antes de enviar el informe).',
    )
    l10n_pe_ic_vat_mismatch = fields.Boolean(
        string='RUC distinto al de la empresa',
        compute='_compute_l10n_pe_ic_vat_mismatch',
    )
    l10n_pe_ic_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Asiento intercompany',
        readonly=True, copy=False,
        help='Cuenta por cobrar a la empresa que asume el gasto contra la cuenta 14 del empleado.',
    )
    # La factura está en otra compañía: se guarda su referencia, no un Many2one que
    # el empleado no podría leer.
    l10n_pe_ic_bill_ref = fields.Char(string='Factura en la otra empresa', readonly=True, copy=False)
    l10n_pe_ic_bill_res_id = fields.Integer(readonly=True, copy=False)

    @api.depends('company_id')
    def _compute_l10n_pe_charged_partner_id(self):
        for expense in self:
            if not expense.l10n_pe_charged_partner_id:
                expense.l10n_pe_charged_partner_id = expense.company_id.partner_id

    @api.depends('company_id')
    def _compute_l10n_pe_ic_allowed_partner_ids(self):
        receivers = self.env['res.company'].sudo().search([('hr_expense_ic_receive', '=', True)])
        for expense in self:
            expense.l10n_pe_ic_allowed_partner_ids = (receivers - expense.company_id).partner_id | expense.company_id.partner_id

    @api.depends('l10n_pe_charged_partner_id', 'company_id')
    def _compute_l10n_pe_ic_customer_vat(self):
        # Un RUC digitado a mano puede dejar el comprobante a nombre de un tercero.
        for expense in self:
            expense.l10n_pe_ic_customer_vat = expense.l10n_pe_is_intercompany and expense.l10n_pe_charged_partner_id.vat

    @api.depends('l10n_pe_ic_customer_vat', 'l10n_pe_charged_partner_id', 'l10n_pe_is_intercompany')
    def _compute_l10n_pe_ic_vat_mismatch(self):
        for expense in self:
            expense.l10n_pe_ic_vat_mismatch = expense.l10n_pe_is_intercompany and (
                _vat_digits(expense.l10n_pe_ic_customer_vat) != _vat_digits(expense.l10n_pe_charged_partner_id.vat)
            )

    @api.onchange('l10n_pe_ic_customer_vat')
    def _onchange_l10n_pe_ic_customer_vat(self):
        if self.l10n_pe_ic_vat_mismatch:
            return {'warning': {
                'title': _('RUC distinto'),
                'message': _('El RUC del adquiriente (%(given)s) no es el de %(company)s (%(vat)s). Verifique que el '
                             'comprobante se emitió a ese RUC.', given=self.l10n_pe_ic_customer_vat,
                             company=self.l10n_pe_charged_partner_id.name, vat=self.l10n_pe_charged_partner_id.vat),
            }}

    @api.depends('l10n_pe_charged_partner_id', 'company_id')
    def _compute_l10n_pe_is_intercompany(self):
        for expense in self:
            expense.l10n_pe_is_intercompany = bool(
                expense.l10n_pe_charged_partner_id
                and expense.l10n_pe_charged_partner_id != expense.company_id.partner_id
            )

    def _l10n_pe_get_charged_company(self):
        """Compañía que asume el gasto (sudo: el empleado no la puede leer)."""
        self.ensure_one()
        return self.env['res.company'].sudo().search([('partner_id', '=', self.l10n_pe_charged_partner_id.id)], limit=1)

    def _l10n_pe_is_done_without_bill(self):
        return super()._l10n_pe_is_done_without_bill() or (
            self.l10n_pe_is_intercompany and self.l10n_pe_ic_move_id.state == 'posted'
        )

    # -------------------------------------------------------------------------
    # Validaciones
    # -------------------------------------------------------------------------

    def _l10n_pe_check_receipt_data(self):
        super()._l10n_pe_check_receipt_data()
        self.filtered('l10n_pe_is_intercompany')._l10n_pe_check_intercompany()

    def _l10n_pe_check_intercompany(self):
        """Antes de enviar y de contabilizar: la empresa que asume el gasto recibe
        gastos, el comprobante está emitido a su RUC y las cuentas existen."""
        errors = []
        for expense in self:
            company = expense._l10n_pe_get_charged_company()
            name = expense.name
            if not company or not company.hr_expense_ic_receive:
                errors.append(_('%(expense)s: %(company)s no recibe gastos de otras empresas.',
                                expense=name, company=expense.l10n_pe_charged_partner_id.name))
                continue
            if expense.l10n_pe_is_advance_refund:
                errors.append(_('%s: una devolución no se puede cargar a otra empresa.', name))
            # Un RUC distinto al de la empresa se permite (se advierte al enviar).
            if not _vat_digits(expense.l10n_pe_ic_customer_vat):
                errors.append(_('%s: indique el RUC del adquiriente que figura en el comprobante.', name))
            if not expense.vendor_id or not expense.l10n_pe_document_reference:
                errors.append(_('%s: indique el proveedor y el comprobante (se registran en la otra empresa).', name))
            if not expense.company_id._get_hr_expense_ic_account('receivable', expense.currency_id):
                errors.append(_('%(expense)s: configure la cuenta por cobrar intercompany de %(company)s.',
                                expense=name, company=expense.company_id.name))
            if not company._get_hr_expense_ic_account('payable', expense.currency_id):
                errors.append(_('%(expense)s: falta la cuenta por pagar intercompany de %(company)s.',
                                expense=name, company=company.name))
            if not company._get_hr_expense_ic_journal():
                errors.append(_('%(expense)s: %(company)s no tiene un diario de compras.', expense=name,
                                company=company.name))
        if errors:
            raise UserError(_('No se pueden cargar estos gastos a otra empresa del grupo:\n%s', '\n'.join(errors)))

    def _l10n_pe_get_duplicated_receipts(self):
        """Un comprobante de otra empresa tampoco puede estar ya registrado allá."""
        duplicated = super()._l10n_pe_get_duplicated_receipts()
        already = {expense.id for expense, _document in duplicated}
        for expense in self.filtered(lambda e: e.l10n_pe_is_intercompany and e.l10n_pe_document_reference
                                     and e.id not in already):
            company = expense._l10n_pe_get_charged_company()
            bill = self.env['account.move'].sudo().search([
                ('company_id', '=', company.id),
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('state', '!=', 'cancel'),
                ('commercial_partner_id', '=', expense.vendor_id.commercial_partner_id.id),
                ('l10n_latam_document_type_id', '=', expense.l10n_pe_document_type_id.id),
                ('ref', '=', expense.l10n_pe_document_reference),
                ('id', '!=', expense.l10n_pe_ic_bill_res_id),
            ], limit=1)
            if bill:
                duplicated.append((expense, bill))
        return duplicated
