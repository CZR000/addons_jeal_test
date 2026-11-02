# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    name_is_manual = fields.Boolean(
        string='Etiqueta editada manualmente',
        default=False,
        copy=False,
        help="Flag interno. Se activa cuando el usuario edita manualmente la "
             "etiqueta (name) de una línea de plazo de pago para que el "
             "compute no la sobrescriba en operaciones posteriores "
             "(confirmar factura, cambiar payment_reference, etc.).",
    )

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _get_installment_payment_term_line(self):
        """Devuelve la account.payment.term.line que corresponde a esta AML de
        tipo payment_term, mapeando por posición (mismo criterio que usa el
        _compute_name nativo para calcular el 'installment #N').

        - Las AMLs payment_term del asiento se ordenan por date_maturity
          (como en nativo, ver account_move_line._compute_name).
        - Las payment.term.line se ordenan por sequence (default order del
          modelo).
        - En términos típicos (detracción/saldo, cuotas mensuales) ambos
          órdenes coinciden. En términos con fechas invertidas respecto al
          sequence podría desalinearse; para JE-AL (detracción) no aplica.
        """
        self.ensure_one()
        move = self.move_id
        pay_term = move.invoice_payment_term_id
        if not pay_term or self.display_type != 'payment_term':
            return self.env['account.payment.term.line']

        term_amls = move.line_ids.filtered(
            lambda l: l.display_type == 'payment_term'
        ).sorted(lambda l: l.date_maturity or date.max)

        if self not in term_amls:
            return self.env['account.payment.term.line']

        index = list(term_amls._ids).index(self.id)
        term_lines = pay_term.line_ids
        if index < len(term_lines):
            return term_lines[index]
        return self.env['account.payment.term.line']

    # -------------------------------------------------------------------------
    # COMPUTE OVERRIDE
    # -------------------------------------------------------------------------

    @api.depends('product_id', 'move_id.ref', 'move_id.payment_reference')
    def _compute_name(self):

        ctx_self = self.with_context(installment_label_recompute=True)
    
        manual_lines = ctx_self.filtered(
            lambda l: l.display_type == 'payment_term' and l.name_is_manual
        )
        manual_snapshot = {line.id: line.name for line in manual_lines}
    
        super(AccountMoveLine, ctx_self)._compute_name()
    
        for line in manual_lines:
            original = manual_snapshot.get(line.id)
            if original is not None and line.name != original:
                line.name = original
    
        payment_term_lines = ctx_self.filtered(
            lambda l: l.display_type == 'payment_term'
            and not l.name_is_manual
            and l.move_id.inalterable_hash is False
        )
        for line in payment_term_lines:
            term_line = line._get_installment_payment_term_line()
            if term_line and term_line.name:
                line.name = term_line.name

    # -------------------------------------------------------------------------
    # WRITE OVERRIDE
    # -------------------------------------------------------------------------

    def write(self, vals):
        # Detectar edición manual de `name` sobre líneas de plazo de pago.
        # Solo se considera manual cuando el write NO viene del propio
        # _compute_name (que se ejecuta con installment_label_recompute=True
        # en el context).
        if (
            'name' in vals
            and 'name_is_manual' not in vals
            and not self.env.context.get('installment_label_recompute')
        ):
            to_mark = self.filtered(
                lambda l: l.display_type == 'payment_term'
                and l.name != vals.get('name')
            )
            if to_mark:
                # Escribimos el flag junto con el resto en el mismo write
                # para las líneas marcadas, y ejecutamos el write original
                # sin el flag para las demás.
                rest = self - to_mark
                res = super(AccountMoveLine, to_mark).write(
                    {**vals, 'name_is_manual': True}
                )
                if rest:
                    res = super(AccountMoveLine, rest).write(vals) and res
                return res
        return super().write(vals)
