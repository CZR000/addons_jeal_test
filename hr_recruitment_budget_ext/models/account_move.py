from odoo import models, _
from odoo.osv import expression


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        result = super().action_post()
        all_warnings = []
        for move in self.filtered(lambda m: m.state == 'posted'):
            all_warnings.extend(move._check_budget_overrun())
        if all_warnings:
            html_lines = ['<ul>']
            for w in all_warnings:
                html_lines.append('<li>' + w.replace('\n', '<br/>') + '</li>')
            html_lines.append('</ul>')
            html_body = (
                '<p style="color:#856404;font-weight:bold;font-size:14px;">'
                '&#9888; Se est&#225; excediendo el l&#237;mite de presupuesto'
                ' en las siguientes l&#237;neas:'
                '</p>'
                + ''.join(html_lines)
            )
            wizard = self.env['budget.warning.wizard'].sudo().create(
                {'message': html_body}
            )
            return {
                'type': 'ir.actions.act_window',
                'name': 'Alerta: Presupuesto Excedido',
                'res_model': 'budget.warning.wizard',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }
        return result

    def _check_budget_overrun(self):
        """
        Revisa si alguna línea de presupuesto validada es excedida.
        En Odoo 18 account_budget usa budget.line / budget.analytic en lugar de
        crossovered.budget.lines / crossovered.budget. Las cuentas analíticas se
        asignan por columnas de plan dinámicas (analytic.plan.fields.mixin).
        """
        warnings = []
        move_date = self.date

        # Recolectar IDs analíticos; las claves pueden ser compuestas "123,456"
        analytic_account_ids = set()
        for line in self.line_ids:
            if line.analytic_distribution:
                for key in line.analytic_distribution.keys():
                    for aid in key.split(','):
                        try:
                            analytic_account_ids.add(int(aid))
                        except (ValueError, TypeError):
                            pass

        if not analytic_account_ids:
            return warnings

        # Obtener columnas de plan dinámicas del modelo budget.line.
        # _get_all_plans() lanza UserError si analytic.project_plan no está
        # configurado; en ese caso no hay nada que revisar.
        try:
            project_plan, other_plans = self.env['account.analytic.plan']._get_all_plans()
        except Exception:
            return warnings
        plan_fnames = [
            plan._column_name()
            for plan in (project_plan + other_plans)
            if plan._column_name() in self.env['budget.line']._fields
        ]
        if not plan_fnames:
            return warnings

        # Buscar budget.line donde al menos una columna de plan coincide
        analytic_domain = expression.OR([
            [(fname, 'in', list(analytic_account_ids))]
            for fname in plan_fnames
        ])
        base_domain = [
            ('date_from', '<=', move_date),
            ('date_to', '>=', move_date),
            ('budget_analytic_state', 'in', ('confirmed', 'done')),
        ]
        budget_lines = self.env['budget.line'].search(
            expression.AND([base_domain, analytic_domain])
        )

        for bl in budget_lines.filtered('is_above_budget'):
            excess = bl.achieved_amount - bl.budget_amount
            sym = bl.currency_id.symbol or ''
            detail = bl.budget_analytic_id.name
            for fname in plan_fnames:
                account = bl[fname]
                if account and account.id in analytic_account_ids:
                    detail += ' / ' + account.name
                    break
            warnings.append(
                detail + '\n'
                + _('  Previsto: %(sym)s %(planned)s | '
                    'Real: %(sym)s %(practical)s | '
                    'Exceso: %(sym)s %(excess)s') % {
                    'sym': sym,
                    'planned': '{:,.2f}'.format(abs(bl.budget_amount)),
                    'practical': '{:,.2f}'.format(abs(bl.achieved_amount)),
                    'excess': '{:,.2f}'.format(abs(excess)),
                }
            )

        return warnings
