from collections import defaultdict
from odoo import _, api, fields, models, exceptions

_STATES = [
    ('draft', 'Borrador'),
    ('in_progress', 'En proceso'),
    ('done', 'Terminado')
]


class ReportLiquidation(models.Model):
    _name = 'report.liquidation'
    _description = 'Liquidaciones'
    _inherit = ['mail.activity.mixin', 'mail.thread']
    _order = 'create_date desc'
    _check_company_auto = True

    name = fields.Char(
        string='Liquidación',
        index='trigram',
        required=True,
        default='Nuevo',
        readonly=True,
        copy=False
    )
    state = fields.Selection(
        string='Estado',
        selection=_STATES,
        default='draft',
        index='btree',
        tracking=True
    )
    date = fields.Date(
        string='Fecha',
        required=True,
        default=lambda self: fields.Date.context_today(self)
    )
    company_id = fields.Many2one(
        string='Compañia',
        comodel_name='res.company',
        default=lambda self: self.env.company,
        readonly=True
    )
    partner_id = fields.Many2one(
        string='Cliente',
        comodel_name='res.partner'
    )
    picking_ids = fields.Many2many(
        string='Traslados',
        comodel_name='stock.picking',
        check_company=True
    )
    operation_ids = fields.One2many(
        string='Operaciones',
        comodel_name='operation.liquidation.line',
        inverse_name='liquidation_id',
        copy=False
    )
    transport_ids = fields.One2many(
        string='Transportes',
        comodel_name='account.liquidation.line',
        inverse_name='liquidation_id',
        domain=[('type', '=', 'transport')],
        copy=False
    )
    process_ids = fields.One2many(
        string='Procesos',
        comodel_name='account.liquidation.line',
        inverse_name='liquidation_id',
        domain=[('type', '=', 'process')],
        copy=False
    )
    invoiced_ids = fields.One2many(
        string='Facturado',
        comodel_name='account.liquidation.line',
        inverse_name='liquidation_id',
        domain=[('type', '=', 'billed')],
        copy=False
    )
    is_readonly = fields.Boolean(
        string='¿Solo lectura?',
        default=False,
        compute='_compute_is_readonly'
    )
    active = fields.Boolean(
        string='¿Activo?',
        default=True
    )

    # ----- HELPERS ----- #
    def _sync_operations_from_pickings(self):
        for rec in self:
            # 1. Tomamos todos los moves de los pickings seleccionados
            target_moves = rec.picking_ids.mapped('move_ids_without_package')

            target_move_ids = set(target_moves.ids)

            # 2. Movimientos ya existentes en líneas
            existing_lines = rec.operation_ids
            existing_move_ids = set(existing_lines.mapped('move_id').ids)

            # 3. Eliminar líneas que ya no correspondan (picking removido)
            lines_to_remove = existing_lines.filtered(lambda l: l.move_id.id not in target_move_ids)

            # 4. Crear líneas faltantes
            moves_to_add = target_moves.filtered(lambda m: m.id not in existing_move_ids)

            commands = []
            commands += [(2, line.id, 0) for line in lines_to_remove]
            # Agregamos
            for move in moves_to_add:
                commands.append((0, 0, {
                    'picking_id': move.picking_id.id,
                    'move_id': move.id,
                }))

            if commands:
                rec.operation_ids = commands

    # ----- ACTIONS ----- #

    def action_done(self):
        self.ensure_one()
        self.write({'state': 'done'})

    def action_to_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})

    def action_to_progress(self):
        self.ensure_one()
        self.write({'state': 'in_progress'})

    # ----- COMPUTES & ONCHANGE METHODS ----- #
    @api.onchange('picking_ids')
    def _onchange_picking_ids(self):
        # Si no está guardado aún, igual funciona porque operation_ids acepta comandos
        self._sync_operations_from_pickings()

    @api.depends('state')
    def _compute_is_readonly(self):
        for rec in self:
            rec.is_readonly = bool(rec.state in ('done', 'in_progress'))

    # ----- CRUD METHODS ----- #
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                seq_date = vals.get('date') or fields.Date.context_today(self)
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'report.liquidation',
                    sequence_date=seq_date,
                ) or 'Nuevo'
            if vals.get('active') is False:
                blocked = self.filtered(lambda r: r.state == 'done')
                if blocked:
                    # Bug fix v16→v18: en el original el `%` estaba fuera
                    # del raise, lo que producía TypeError en lugar de
                    # UserError. Se preserva la intención del autor.
                    raise exceptions.UserError(_(
                        'No puedes archivar una liquidación en estado Realizado.\n'
                        'Registros: %s'
                    ) % ', '.join(blocked.mapped('name')))
        return super().create(vals_list)
    
    def write(self, vals):
        res = super().write(vals)
        if 'picking_ids' in vals:
            self._sync_operations_from_pickings()
        return res
