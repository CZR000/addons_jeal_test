from odoo import api, models


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    @api.depends('company_id', 'vendor_id.l10n_latam_identification_type_id')
    def _compute_l10n_pe_available_document_type_ids(self):
        super()._compute_l10n_pe_available_document_type_ids()

    def _l10n_pe_get_vendor_accepted_document_types(self):
        self.ensure_one()
        return self.vendor_id.l10n_latam_identification_type_id.invoice_validation_document

    def _l10n_pe_get_document_types_domain(self):
        domain = super()._l10n_pe_get_document_types_domain()
        accepted = self._l10n_pe_get_vendor_accepted_document_types()
        return domain + [('id', 'in', accepted.ids)] if accepted else domain
