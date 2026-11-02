from odoo import models, Command


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    # ------------------------------------------------------------------
    # Override _prepare_bills_vals (own_account mode only).
    # In v18, _do_approve already auto-creates moves via _do_create_moves,
    # so no _do_approve override is needed.
    # Here we:
    #   1. Set vendor partner (overrides employee address).
    #   2. Set document type for purchase register.
    #   3. Expand extra lines when use_extra_lines=True.
    #   4. Set move_type='entry' when all expenses exclude purchase register.
    # ------------------------------------------------------------------
    def _prepare_bills_vals(self):
        vals = super()._prepare_bills_vals()

        # 1. Set vendor partner
        for expense in self.expense_line_ids:
            if hasattr(expense, 'vendor_id') and expense.vendor_id:
                vals['partner_id'] = expense.vendor_id.id
                break

        # 2. Set document type for purchase register
        if 'l10n_latam_document_type_id' in self.env['account.move']._fields:
            for expense in self.expense_line_ids:
                if hasattr(expense, 'l10n_latam_document_type_id') and expense.l10n_latam_document_type_id:
                    vals['l10n_latam_document_type_id'] = expense.l10n_latam_document_type_id.id
                    break

        # 3. Expand extra lines
        has_extra = any(
            getattr(exp, 'use_extra_lines', False) and exp.extra_line_ids
            for exp in self.expense_line_ids
        )
        if has_extra:
            expanded = []
            for expense in self.expense_line_ids:
                if getattr(expense, 'use_extra_lines', False) and expense.extra_line_ids:
                    for extra in expense.extra_line_ids:
                        expanded.append(Command.create(extra._prepare_move_line_vals()))
                else:
                    expanded.append(Command.create(expense._prepare_move_lines_vals()))
            vals['line_ids'] = expanded

        # 4. Registro de compras
        if self.expense_line_ids and hasattr(self.expense_line_ids[0], 'include_in_purchase_register'):
            all_excluded = all(
                not exp.include_in_purchase_register
                for exp in self.expense_line_ids
            )
            if all_excluded:
                vals['move_type'] = 'entry'

        return vals
