# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_compensation_move = fields.Boolean(
        string='Es asiento de compensación',
        copy=False,
        default=False,
        help='Marca los asientos generados por el wizard de compensación.',
    )
    compensated_invoice_ids = fields.Many2many(
        comodel_name='account.move',
        relation='account_move_compensation_rel',
        column1='compensation_id',
        column2='invoice_id',
        string='Facturas compensadas',
        copy=False,
        help='Facturas de cliente y proveedor que este asiento compensa.',
    )
    compensation_move_ids = fields.Many2many(
        comodel_name='account.move',
        relation='account_move_compensation_rel',
        column1='invoice_id',
        column2='compensation_id',
        string='Compensaciones aplicadas',
        copy=False,
        help='Asientos de compensación que afectan a esta factura.',
    )
    compensation_count = fields.Integer(
        compute='_compute_compensation_count',
        string='# Compensaciones',
    )

    @api.depends('compensation_move_ids')
    def _compute_compensation_count(self):
        for move in self:
            move.compensation_count = len(move.compensation_move_ids)

    # -------------------------------------------------------------------------
    # Botones
    # -------------------------------------------------------------------------
    def action_open_compensation_wizard(self):
        """Abre el wizard de compensación desde una factura de cliente o proveedor."""
        self.ensure_one()
        if self.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(_(
                'La compensación solo aplica en facturas de cliente o proveedor.'
            ))
        if self.state != 'posted':
            raise UserError(_('La factura debe estar publicada.'))
        if self.payment_state not in ('not_paid', 'partial'):
            raise UserError(_(
                'La factura debe estar sin pagar o pagada parcialmente.'
            ))
        if self.currency_id.is_zero(self.amount_residual):
            raise UserError(_('La factura no tiene saldo pendiente.'))
        if not self.partner_id:
            raise UserError(_('La factura debe tener un socio asignado.'))

        company = self.company_id
        # Validar configuración
        Wizard = self.env['l10n_pe.compensation.wizard']
        Wizard._check_configuration(company)

        # Calcular tipo de cambio del día contable (fecha del asiento)
        today = fields.Date.context_today(self)
        if self.currency_id == company.currency_id:
            currency_rate = 1.0
        else:
            currency_rate = self.env['res.currency']._get_conversion_rate(
                from_currency=self.currency_id,
                to_currency=company.currency_id,
                company=company,
                date=today,
            )

        # Crear el wizard con todos los defaults necesarios
        wizard = Wizard.create({
            'move_id': self.id,
            'journal_id': company.compensation_journal_id.id,
            'date': today,
            'currency_rate': currency_rate,
        })
        wizard.load_counterparts()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Aplicar Compensación'),
            'res_model': 'l10n_pe.compensation.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_compensations(self):
        """Smart button opcional para ver los asientos vinculados."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Compensaciones aplicadas'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.compensation_move_ids.ids)],
        }

    def action_reverse_compensation(self):
        """Revierte un asiento de compensación: rompe conciliación y crea reverso."""
        self.ensure_one()
        if not self.is_compensation_move:
            raise UserError(_('Solo se puede reversar un asiento de compensación.'))
        if self.state != 'posted':
            raise UserError(_('El asiento debe estar publicado para reversarlo.'))

        self._break_compensation_reconciliation()

        default_values = [{
            'date': fields.Date.context_today(self),
            'ref': _('REVERSO %s') % (self.name or ''),
        }]
        reverse_moves = self._reverse_moves(
            default_values_list=default_values,
            cancel=True,
        )
        reverse_moves.write({'is_compensation_move': False})

        self.message_post(body=_(
            'Compensación revertida mediante el asiento %s.'
        ) % ', '.join(reverse_moves.mapped('name')))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Reverso de Compensación'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': reverse_moves[:1].id,
        }

    # -------------------------------------------------------------------------
    # Conciliación automática al publicar
    # -------------------------------------------------------------------------
    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered('is_compensation_move'):
            try:
                move._reconcile_compensation_lines()
            except Exception as e:
                _logger.exception(
                    'Error al conciliar compensación %s: %s', move.name, e
                )
                move.message_post(body=_(
                    'No se pudo conciliar automáticamente: %s. '
                    'Deberá conciliar manualmente desde cada factura.'
                ) % e)
        return posted

    def _reconcile_compensation_lines(self):
        """Concilia las líneas del asiento de compensación con las líneas AR/AP
        de cada factura compensada.

        Siempre se usa no_exchange_difference=True para evitar que Odoo genere
        asientos adicionales de diferencia cambiaria. El asiento de compensación
        ya maneja la diferencia mediante la línea a la cuenta 776/676 configurada
        (opción 'Aplicar como diferencia de cambio') o mediante absorción en el
        origen (opción 'Dejar como saldo pendiente')."""
        self.ensure_one()
        if not self.is_compensation_move:
            return

        for invoice in self.compensated_invoice_ids:
            invoice_ar_ap_lines = invoice.line_ids.filtered(
                lambda l: l.account_id.account_type in (
                    'asset_receivable', 'liability_payable'
                ) and not l.reconciled
            )
            if not invoice_ar_ap_lines:
                continue

            matching_accounts = invoice_ar_ap_lines.mapped('account_id')
            comp_lines = self.line_ids.filtered(
                lambda l: l.account_id in matching_accounts
                and l.partner_id == invoice.partner_id
                and not l.reconciled
            )
            if not comp_lines:
                continue

            try:
                lines_to_reconcile = invoice_ar_ap_lines + comp_lines
                lines_to_reconcile.with_context(
                    no_exchange_difference=True
                ).reconcile()
            except Exception as e:
                _logger.warning(
                    'No se pudo conciliar factura %s con compensación %s: %s',
                    invoice.name, self.name, e,
                )

    def _break_compensation_reconciliation(self):
        """Rompe la conciliación entre el asiento de compensación y las facturas."""
        self.ensure_one()
        comp_lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type in (
                'asset_receivable', 'liability_payable'
            )
        )
        for line in comp_lines:
            partials = line.matched_debit_ids + line.matched_credit_ids
            if partials:
                partials.unlink()
