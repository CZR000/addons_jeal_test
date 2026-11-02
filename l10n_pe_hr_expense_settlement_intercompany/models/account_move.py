from markupsafe import Markup

from odoo import _, fields, models, Command
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Datos de la empresa de origen: el contacto (compartido) y textos, no
    # registros de otra compañía que la contadora no podría leer.
    l10n_pe_ic_origin_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Gasto recibido de',
        readonly=True, copy=False, index='btree_not_null',
        help='Empresa del grupo cuyo empleado rindió este comprobante (pagó el gasto por esta empresa).',
    )
    l10n_pe_ic_origin_ref = fields.Char(string='Informe de origen', readonly=True, copy=False)
    l10n_pe_ic_payable_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Deuda intercompany',
        readonly=True, copy=False,
        help='Asiento que reconoce la deuda con la empresa que pagó el gasto (Debe 42 / Haber 46).',
    )

    def _post(self, soft=True):
        posted = super()._post(soft)
        posted.filtered(lambda move: (
            move.l10n_pe_ic_origin_partner_id and move.move_type == 'in_invoice' and not move.l10n_pe_ic_payable_move_id
        ))._l10n_pe_recognize_ic_payable()
        return posted

    def button_draft(self):
        payable_moves = self.l10n_pe_ic_payable_move_id.filtered(lambda move: move.state == 'posted')
        res = super().button_draft()
        if payable_moves:
            payable_moves.button_draft()
            payable_moves.button_cancel()
            self.filtered('l10n_pe_ic_payable_move_id').l10n_pe_ic_payable_move_id = False
        return res

    def _l10n_pe_recognize_ic_payable(self):
        """La empresa que asume el gasto no le paga al proveedor (lo pagó el empleado
        de la otra empresa): Debe 42 proveedor / Haber cuenta por pagar intercompany
        a nombre de esa empresa, con la referencia de su informe, conciliado con la
        factura."""
        for bill in self:
            company = bill.company_id
            payable_lines = bill.line_ids.filtered(
                lambda line: line.account_id.account_type == 'liability_payable' and not line.reconciled
            )
            account = company._get_hr_expense_ic_account('payable', bill.currency_id)
            journal = company.hr_expense_settlement_journal_id or self._l10n_pe_get_ic_payable_journal(company)
            if not account or not journal:
                raise UserError(_(
                    'Configure en %s la cuenta por pagar intercompany y el diario de liquidación de la rendición de '
                    'gastos para registrar la deuda con la empresa que pagó el gasto.', company.name,
                ))
            label = _('%(ref)s · pagado por %(origin)s (%(sheet)s)', ref=bill.ref or bill.name,
                      origin=bill.l10n_pe_ic_origin_partner_id.name, sheet=bill.l10n_pe_ic_origin_ref)
            line_vals = [Command.create({
                'name': label,
                'account_id': line.account_id.id,
                'partner_id': line.partner_id.id,
                'currency_id': line.currency_id.id,
                'amount_currency': -line.amount_currency,
                'balance': -line.balance,
            }) for line in payable_lines]
            line_vals.append(Command.create({
                'name': label,
                'account_id': account.id,
                'partner_id': bill.l10n_pe_ic_origin_partner_id.id,
                'currency_id': bill.currency_id.id,
                'amount_currency': sum(payable_lines.mapped('amount_currency')),
                'balance': sum(payable_lines.mapped('balance')),
            }))
            move = self.create({
                'move_type': 'entry',
                'company_id': company.id,
                'journal_id': journal.id,
                'date': bill.date,
                'ref': bill.l10n_pe_ic_origin_ref,
                'line_ids': line_vals,
            })
            move.action_post()
            for line in payable_lines:
                (line + move.line_ids.filtered(lambda counterpart: (
                    counterpart.account_id == line.account_id and counterpart.partner_id == line.partner_id
                    and not counterpart.reconciled
                ))).reconcile()
            bill.l10n_pe_ic_payable_move_id = move
            bill.message_post(body=Markup(_('Deuda con %(origin)s registrada: %(move)s')) % {
                'origin': bill.l10n_pe_ic_origin_partner_id.name, 'move': move._get_html_link(),
            })

    def _l10n_pe_get_ic_payable_journal(self, company):
        """Diario general para la deuda intercompany si la empresa no tiene diario de
        liquidación: uno que no pida aprobación de asientos (account_move_approval),
        porque el asiento se publica solo al publicar la factura."""
        journals = self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(company),
            ('type', '=', 'general'),
        ])
        if 'requires_approval' in journals._fields:
            return journals.filtered(lambda journal: not journal.requires_approval)[:1]
        return journals[:1]

    def _l10n_pe_ic_withholding_warnings(self):
        """Detracción y retención quedan fuera de esta etapa: solo se avisa."""
        self.ensure_one()
        warnings = []
        if 'l10n_pe_is_detraction' in self._fields and self.l10n_pe_is_detraction:
            warnings.append(_('El comprobante está sujeto a detracción: gestiónela antes de publicar.'))
        company = self.company_id
        if 'is_retention' in company._fields and company.is_retention \
                and abs(self.amount_total_signed) >= (company.amount_minimum_retention or 0.0):
            warnings.append(_('%s es agente de retención: verifique si corresponde retener.', company.name))
        return warnings
