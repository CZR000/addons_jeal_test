# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    """Campos espejo del gasto origen en la factura de proveedor
    generada por ``hr.expense.sheet``.

    No redefinimos los campos LATAM ya expuestos por la localización
    oficial: ``l10n_latam_document_type_id``, ``l10n_latam_document_number``,
    ``l10n_pe_edi_operation_type``, ``l10n_pe_usage_type_id``,
    ``l10n_pe_dua_invoice_id``, ``l10n_pe_service_modality``,
    ``l10n_pe_sunat_transaction_type``, ``expense_sheet_id`` (nativo de
    ``hr_expense``).
    """

    _inherit = 'account.move'

    igv_assignment_id = fields.Many2one(
        comodel_name='l10n.pe.igv.assignment',
        string='Asignación de IGV',
        copy=False,
        help='Espejo del gasto origen.',
    )
    in_purchase_register = fields.Boolean(
        string='En Registro de Compras',
        compute='_compute_in_purchase_register',
        store=True,
        readonly=True,
        help='Derivado de la asignación de IGV.',
    )
    ecpn_id = fields.Many2one(
        comodel_name='l10n.pe.ecpn.category',
        string='Categoría ECPN',
        copy=False,
        help='Espejo informativo del gasto origen.',
    )
    merchant_id = fields.Many2one(
        comodel_name='res.partner',
        string='Comerciante',
        copy=False,
        help='Espejo informativo del gasto origen.',
    )

    @api.depends('igv_assignment_id', 'igv_assignment_id.affects_register')
    def _compute_in_purchase_register(self):
        for move in self:
            move.in_purchase_register = bool(
                move.igv_assignment_id
                and move.igv_assignment_id.affects_register
            )
