from odoo import api

_DOMAIN = "['|', '|', ('company_id', 'in', company_ids), ('company_id', '=', False), ('is_disbursement_request', '=', True)]"
_ORIGINAL_DOMAIN = "['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]"


def _patch_payment_company_rule(env):
    """Permite que las solicitudes de desembolso sean visibles cross-company.

    Modifica la regla global de account.payment para agregar un OR por
    is_disbursement_request, de modo que cualquier usuario con acceso a
    account.payment pueda ver los desembolsos independientemente de la empresa.

    No se puede hacer desde XML porque la regla tiene noupdate=True.
    """
    rule = env.ref('account.account_payment_comp_rule', raise_if_not_found=False)
    if rule:
        rule.write({'domain_force': _DOMAIN})

    # Limpiar regla de grupo obsoleta que bloqueaba el flujo
    old_rule = env.ref(
        'hr_expense_cust.rule_disbursement_approver_all_companies',
        raise_if_not_found=False,
    )
    if old_rule:
        old_rule.unlink()


def post_init_hook(env):
    """Corre al instalar el módulo (instalación fresca)."""
    _patch_payment_company_rule(env)


def uninstall_hook(env):
    """Restaura la regla original al desinstalar el módulo."""
    rule = env.ref('account.account_payment_comp_rule', raise_if_not_found=False)
    if rule:
        rule.write({'domain_force': _ORIGINAL_DOMAIN})
