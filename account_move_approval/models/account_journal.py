# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    requires_approval = fields.Boolean(
        string='Requiere Aprobación',
        default=False,
        help='Si está activado, los asientos contables manuales creados en este diario '
             'requerirán aprobación antes de ser publicados. '
             'Los usuarios con rol de Aprobador podrán publicar directamente.'
    )
