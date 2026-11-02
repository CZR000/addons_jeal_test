from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _requires_invoice_validation_document(self):
        # Los comprobantes fuera del Registro de Compras (gastos sin sustento) no
        # llevan tipo de documento: no se les exige uno aceptado para el socio.
        return (
            super()._requires_invoice_validation_document()
            and self.journal_id != self.company_id.hr_expense_non_register_journal_id
        )
