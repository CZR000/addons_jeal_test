from odoo import api, SUPERUSER_ID

_DOMAIN = "['|', '|', ('company_id', 'in', company_ids), ('company_id', '=', False), ('is_disbursement_request', '=', True)]"
_ORIGINAL_DOMAIN = "['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Actualizar regla global de empresa para visibilidad cross-company de desembolsos
    rule = env.ref('account.account_payment_comp_rule', raise_if_not_found=False)
    if rule:
        rule.write({'domain_force': _DOMAIN})

    # Eliminar regla de grupo antigua si aún existe
    old_rule = env.ref(
        'hr_expense_cust.rule_disbursement_approver_all_companies',
        raise_if_not_found=False,
    )
    if old_rule:
        old_rule.unlink()
