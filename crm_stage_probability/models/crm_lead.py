from odoo import api, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    @api.onchange('stage_id')
    def _onchange_stage_id_probability(self):
        for lead in self:
            if lead.stage_id:
                lead.probability = lead.stage_id.stage_probability

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals and 'probability' not in vals:
            stage = self.env['crm.stage'].browse(vals['stage_id'])
            if stage:
                self.env.cr.execute(
                    "UPDATE crm_lead SET probability = %s WHERE id IN %s",
                    (stage.stage_probability, tuple(self.ids))
                )
                self.invalidate_recordset(['probability'])
        return res