# -*- coding: utf-8 -*-
from odoo import fields, models


class ClosingEntryConfirmWizard(models.TransientModel):
    _name = "closing.entry.confirm.wizard"
    _description = "Confirmación de Asiento de Cierre sin Analítica"

    closing_wizard_id = fields.Many2one(
        comodel_name="closing.entry.wizard",
        string="Asistente de Cierre",
        required=True,
        ondelete="cascade",
    )

    message = fields.Text(string="Mensaje", readonly=True)

    def action_confirm(self):
        """Reintenta la generación saltándose la política analítica.

        El bypass es explícito y acotado a esta llamada: se propaga por
        contexto y sólo lo interpreta `AccountMoveLine._check_analytic_required`.
        La decisión de publicar o no depende de `auto_post` del asistente
        original, no de esta confirmación.
        """
        self.ensure_one()
        return self.closing_wizard_id.with_context(
            closing_entry_force_create=True,
            skip_analytic_policy_check=True,
        ).action_generate_entries()
