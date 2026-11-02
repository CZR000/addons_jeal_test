# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import AccessError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        if not self.env.su and not user.has_group("restrict_journal_creation.group_allow_create_account_journal"):
            raise AccessError(_(
                "No tienes permiso para crear diarios contables.\n"
                "Solicita al administrador que te asigne el grupo: 'Puede crear diarios contables'."
            ))

        return super(AccountJournal, self).create(vals_list)
