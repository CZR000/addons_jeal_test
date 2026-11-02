# -*- coding: utf-8 -*-
from odoo import api, fields, models


class L10nPeEcpnCategory(models.Model):
    """Rubro interno del cliente para el reporte ECPN.

    Catálogo puramente interno de Empiria — no hay data precargada,
    la puebla el propio cliente.
    """

    _name = 'l10n.pe.ecpn.category'
    _description = 'Categoría ECPN (Empiria)'
    _order = 'code'

    code = fields.Char(string='Código', required=True, index=True)
    name = fields.Char(string='Nombre', required=True, translate=True)
    active = fields.Boolean(string='Activo', default=True)

    _sql_constraints = [
        (
            'code_uniq',
            'unique(code)',
            'El código de la categoría ECPN debe ser único.',
        ),
    ]

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            if rec.code:
                rec.display_name = f'[{rec.code}] {rec.name or ""}'.strip()
            else:
                rec.display_name = rec.name or ''
