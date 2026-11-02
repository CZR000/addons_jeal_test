# -*- coding: utf-8 -*-
from odoo import fields, models

# Opciones de vigencia del enlace (horas, etiqueta).
SCA_LINK_VALIDITY = [
    ('24', "24 horas"),
    ('48', "48 horas"),
    ('72', "3 días"),
    ('168', "1 semana"),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    sca_credit_approver_id = fields.Many2one(
        'res.users',
        string="Aprobador de crédito",
        help="Usuario único que recibe por correo las solicitudes de "
             "aprobación de ventas al crédito. Debe tener un correo válido.",
    )
    sca_link_validity_hours = fields.Integer(
        string="Vigencia del enlace (horas)",
        default=72,
        help="Horas durante las cuales funcionan los botones Aprobar / "
             "Rechazar del correo. Vencido, el vendedor reenvía la solicitud.",
    )
    sca_require_approval_overdue = fields.Boolean(
        string="Pedir aprobación si el cliente tiene facturas vencidas",
        default=True,
    )
    sca_overdue_grace_days = fields.Integer(
        string="Días de gracia para facturas vencidas",
        default=0,
        help="Una factura vencida solo exige aprobación cuando su atraso "
             "supera estos días. 0 = cualquier atraso.",
    )
    sca_debt_scope = fields.Selection([
        ('invoices', "Facturas pendientes de cobro"),
        ('invoices_orders', "Facturas pendientes + pedidos confirmados sin facturar"),
        ('all', "Todo, incluso facturas en borrador"),
    ], string="Qué cuenta como deuda del cliente",
        default='invoices_orders', required=True,
        help="Los anticipos y notas de crédito sin aplicar siempre se restan.")
