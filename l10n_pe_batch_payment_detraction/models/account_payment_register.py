# -*- coding: utf-8 -*-
from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _get_batch_communication(self, batch_result):
        moves = batch_result['lines'].move_id
        refs = moves.filtered('ref').mapped('ref')
        if refs:
            return ' '.join(refs) if len(refs) == 1 else ', '.join(refs)
        return super()._get_batch_communication(batch_result)
