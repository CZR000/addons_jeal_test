# -*- coding: utf-8 -*-
from odoo import api, fields, models


class L10nPeIgvAssignment(models.Model):
    """Asignación / destino del IGV en un comprobante de gasto.

    Decide si el IGV afecta el Registro de Compras (con crédito fiscal)
    o va al costo.

    Versión autónoma: NO hereda de ``model.sunat.catalog`` (que expondría
    ``l10n_pe_catalog``). Se declaran los campos base directamente para
    no arrastrar la dependencia de terceros.
    """

    _name = 'l10n.pe.igv.assignment'
    _description = 'Asignación de IGV (SUNAT)'
    _order = 'code'

    code = fields.Char(
        string='Código',
        required=True,
        index=True,
    )
    name = fields.Char(
        string='Nombre',
        required=True,
        translate=True,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
    affects_register = fields.Boolean(
        string='Afecta Registro de Compras',
        default=True,
        help='Si está marcado, el gasto con esta asignación se incluye en el '
             'Registro de Compras (crédito fiscal). Si no, el IGV va al costo.',
    )
    tax_group_id = fields.Many2one(
        comodel_name='account.tax.group',
        string='Grupo de Impuestos',
        help='Opcional. Mapeo automático a impuestos por grupo.',
    )

    _sql_constraints = [
        (
            'code_uniq',
            'unique(code)',
            'El código de la asignación de IGV debe ser único.',
        ),
    ]

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            if rec.code:
                rec.display_name = f'[{rec.code}] {rec.name or ""}'.strip()
            else:
                rec.display_name = rec.name or ''
