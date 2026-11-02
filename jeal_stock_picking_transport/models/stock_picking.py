# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    transportista_id = fields.Many2one(
        'res.partner',
        string='Transportista',
    )
    guias_grr = fields.Char(
        string='Guías GRR',
        help='Guía de Remisión Remitente. Ejemplo: T001-00001234',
    )
    guias_gtr = fields.Char(
        string='Guías GTR',
        help='Guía de Remisión Transportista. Ejemplo: EOO1-09876543',
    )
    placa = fields.Char(
        string='Placa',
    )
    ticket_pesaje = fields.Char(
        string='Ticket de pesaje',
        help='Solo números. Único por compañía (excepto transferencias canceladas). '
             'Ejemplo: 27781',
        index=True,
        copy=False,
    )

    @api.constrains('ticket_pesaje')
    def _check_ticket_pesaje(self):
        for rec in self:
            if rec.ticket_pesaje and not rec.ticket_pesaje.strip().isdigit():
                raise ValidationError(
                    'El Ticket de pesaje solo puede contener números. '
                    'Valor ingresado: "%s"' % rec.ticket_pesaje
                )

    @api.constrains('ticket_pesaje', 'company_id', 'state')
    def _check_ticket_pesaje_unico(self):
        """El ticket de pesaje no puede repetirse en la misma compañía.
        Las transferencias canceladas no cuentan (su ticket se puede reutilizar)."""
        for rec in self:
            ticket = (rec.ticket_pesaje or '').strip()
            if not ticket or rec.state == 'cancel':
                continue
            dup = self.sudo().search([
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('ticket_pesaje', '=', ticket),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if dup:
                raise ValidationError(_(
                    'El Ticket de pesaje "%(ticket)s" ya está registrado en la '
                    'transferencia %(picking)s de la compañía %(company)s.',
                    ticket=ticket, picking=dup.name, company=rec.company_id.name,
                ))