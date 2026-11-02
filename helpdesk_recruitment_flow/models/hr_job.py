# -*- coding: utf-8 -*-
from odoo import fields, models, _


class HrJob(models.Model):
    _inherit = 'hr.job'

    helpdesk_ticket_count = fields.Integer(
        string='Tickets de Mesa de Ayuda',
        compute='_compute_helpdesk_ticket_count',
    )

    def _compute_helpdesk_ticket_count(self):
        ticket_data = self.env['helpdesk.ticket']._read_group(
            domain=[('x_perfil_id', 'in', self.ids)],
            groupby=['x_perfil_id'],
            aggregates=['__count'],
        )
        count_map = {job.id: count for job, count in ticket_data}
        for job in self:
            job.helpdesk_ticket_count = count_map.get(job.id, 0)

    def action_view_helpdesk_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tickets - %s') % self.name,
            'res_model': 'helpdesk.ticket',
            'view_mode': 'list,form',
            'domain': [('x_perfil_id', '=', self.id)],
            'context': {'default_x_perfil_id': self.id},
        }
