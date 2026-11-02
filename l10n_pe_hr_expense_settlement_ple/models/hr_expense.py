from odoo import models


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    def _l10n_pe_get_document_types_domain(self):
        # document_in_supplier_invoice (dependencia de ple_purchase_book) asocia
        # cada tipo de documento a un diario de compras: solo los de la compañía.
        return super()._l10n_pe_get_document_types_domain() + [
            '|', ('account_journal_id', '=', False), ('account_journal_id.company_id', '=', self.company_id.id),
        ]
