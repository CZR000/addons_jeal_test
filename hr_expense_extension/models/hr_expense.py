# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


# Formato base de serie (SUNAT): 4 caracteres alfanuméricos en mayúsculas.
# El primer carácter identifica el tipo (F=Factura, B=Boleta, ...) según
# el tipo de documento; la validación fina por tipo queda como mejora
# futura (ver _check_reference_format).
SERIE_REGEX = re.compile(r'^[A-Z0-9]{4}$')
NUMBER_REGEX = re.compile(r'^\d{1,8}$')


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    # ------------------------------------------------------------------
    # Campos SUNAT
    # ------------------------------------------------------------------
    # NOTA: el campo con lógica de proveedor es el ``vendor_id`` NATIVO
    # de hr.expense (definido por Odoo). Toda la generación de factura,
    # agrupación y control de duplicados usa ese nativo. La vista de
    # este módulo lo fuerza visible también en own_account, porque en
    # Perú SUNAT exige el proveedor en el Registro de Compras.

    l10n_latam_document_type_id = fields.Many2one(
        comodel_name='l10n_latam.document.type',
        string='Tipo de documento',
        domain="[('country_id.code', '=', 'PE')]",
        help='Tipo de comprobante SUNAT. Si está informado, al aprobar el '
             'reporte de gastos se generará una factura de proveedor '
             '(account.move tipo in_invoice).',
    )
    document_serie = fields.Char(
        string='Serie',
        size=4,
        help='Serie del comprobante (ej. F001, B001).',
    )
    document_number = fields.Char(
        string='Número',
        size=8,
        help='Correlativo del comprobante. Se rellena automáticamente '
             'a 8 dígitos con ceros a la izquierda.',
    )
    igv_assignment_id = fields.Many2one(
        comodel_name='l10n.pe.igv.assignment',
        string='Asignación de IGV',
        help='Destino del IGV (GE, GN, GG, etc.). Decide crédito fiscal vs. '
             'costo.',
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
        help='Rubro interno del cliente para el reporte ECPN. Opcional.',
    )
    merchant_id = fields.Many2one(
        comodel_name='res.partner',
        string='Comerciante',
        help='Comerciante distinto del emisor. Solo informativo — no cambia '
             'el partner del asiento ni de la factura.',
    )

    use_multiple_lines = fields.Boolean(
        string='Usar múltiples líneas',
        help='Habilita el desglose del comprobante por líneas '
             '(ver pestaña "Líneas del comprobante").',
    )
    line_ids = fields.One2many(
        comodel_name='hr.expense.line',
        inverse_name='expense_id',
        string='Líneas del comprobante',
        copy=True,
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('igv_assignment_id', 'igv_assignment_id.affects_register')
    def _compute_in_purchase_register(self):
        for expense in self:
            expense.in_purchase_register = bool(
                expense.igv_assignment_id
                and expense.igv_assignment_id.affects_register
            )

    @api.depends(
        'use_multiple_lines',
        'line_ids',
        'line_ids.price_subtotal',
    )
    def _compute_total_amount(self):
        """Cuando ``use_multiple_lines=True`` **y** existen líneas, el
        total se calcula como la suma de los subtotales de las líneas.
        En caso contrario, delegamos al ``super()``.
        """
        expenses_with_lines = self.filtered(
            lambda e: e.use_multiple_lines and e.line_ids
        )
        for expense in expenses_with_lines:
            total = sum(expense.line_ids.mapped('price_subtotal'))
            expense.total_amount = total
            qty = expense.quantity or 1.0
            expense.price_unit = total / qty

        remaining = self - expenses_with_lines
        if remaining:
            super(HrExpense, remaining)._compute_total_amount()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Dos ajustes al crear:

        1. Bugfix: cuando ``use_multiple_lines=True`` y ``price_unit`` no
           viene en vals, se inyecta ``price_unit=0.0`` para evitar el
           fallo del INSERT por NOT NULL.
        2. Normalización de serie / número (padding + upper) para que
           aplique también en creación por RPC / import.
        """
        for vals in vals_list:
            if vals.get('use_multiple_lines') and 'price_unit' not in vals:
                vals['price_unit'] = 0.0
            self._normalize_document_reference(vals)
        return super().create(vals_list)

    def write(self, vals):
        """Normaliza serie / número también al escribir (RPC / import)."""
        self._normalize_document_reference(vals)
        return super().write(vals)

    @staticmethod
    def _normalize_document_reference(vals):
        """Aplica upper() a la serie y padding a 8 dígitos al número,
        mutando ``vals`` en sitio.
        """
        serie = vals.get('document_serie')
        if serie:
            vals['document_serie'] = serie.strip().upper()
        number = vals.get('document_number')
        if number:
            num = number.strip()
            if num.isdigit():
                vals['document_number'] = num.zfill(8)

    # ------------------------------------------------------------------
    # Onchange — feedback inmediato en el formulario
    # ------------------------------------------------------------------
    @api.onchange('document_number')
    def _onchange_document_number_padding(self):
        for expense in self:
            num = (expense.document_number or '').strip()
            if num and num.isdigit():
                expense.document_number = num.zfill(8)

    @api.onchange('document_serie')
    def _onchange_document_serie_upper(self):
        for expense in self:
            if expense.document_serie:
                expense.document_serie = expense.document_serie.strip().upper()

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains(
        'document_serie', 'document_number', 'l10n_latam_document_type_id',
    )
    def _check_reference_format(self):
        """Valida el formato de serie / número cuando hay tipo de
        documento informado.
        """
        for expense in self:
            if not expense.l10n_latam_document_type_id:
                continue
            serie = expense.document_serie or ''
            number = expense.document_number or ''

            if not serie or not number:
                raise ValidationError(_(
                    'Debe indicar Serie y Número para el comprobante '
                    'del gasto "%(name)s".',
                    name=expense.name or expense.display_name,
                ))

            if not SERIE_REGEX.match(serie):
                raise ValidationError(_(
                    'La Serie "%(serie)s" no cumple el formato SUNAT '
                    '(4 caracteres alfanuméricos en mayúsculas).',
                    serie=serie,
                ))
            if not NUMBER_REGEX.match(number):
                raise ValidationError(_(
                    'El Número "%(number)s" no cumple el formato SUNAT '
                    '(hasta 8 dígitos numéricos).',
                    number=number,
                ))

    @api.constrains(
        'vendor_id',
        'l10n_latam_document_type_id',
        'document_serie',
        'document_number',
        'company_id',
    )
    def _check_duplicate_document(self):
        """Bloquea duplicidad de comprobante por proveedor/compañía.

        Solo aplica cuando los cuatro valores están informados.
        Considera también gastos archivados.
        """
        for expense in self:
            if not (
                expense.vendor_id
                and expense.l10n_latam_document_type_id
                and expense.document_serie
                and expense.document_number
            ):
                continue
            duplicate = self.with_context(active_test=False).search(
                [
                    ('id', '!=', expense.id),
                    ('company_id', '=', expense.company_id.id),
                    ('vendor_id', '=', expense.vendor_id.id),
                    (
                        'l10n_latam_document_type_id',
                        '=',
                        expense.l10n_latam_document_type_id.id,
                    ),
                    ('document_serie', '=', expense.document_serie),
                    ('document_number', '=', expense.document_number),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(_(
                    'Ya existe un gasto con el mismo comprobante '
                    '%(serie)s-%(number)s para el proveedor '
                    '%(vendor)s (gasto: %(ref)s).',
                    serie=expense.document_serie,
                    number=expense.document_number,
                    vendor=expense.vendor_id.display_name,
                    ref=duplicate.display_name,
                ))
