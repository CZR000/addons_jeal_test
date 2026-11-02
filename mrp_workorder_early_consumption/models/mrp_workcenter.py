# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    wo_consumable_line_ids = fields.One2many(
        comodel_name='mrp.workcenter.consumable',
        inverse_name='workcenter_id',
        string='Consumibles de centro de trabajo',
    )


class MrpWorkcenterConsumable(models.Model):
    """Producto que el centro de trabajo gasta al operar y que no forma parte
    de la lista de materiales. Al terminar cada orden de trabajo en este
    centro se consume:

        cantidad = cantidad producida * qty_per_unit + qty_fixed

    La cantidad producida está en la unidad de medida de la orden de
    fabricación; el resultado, en la unidad de medida del producto consumible.
    """
    _name = 'mrp.workcenter.consumable'
    _description = 'Consumible de centro de trabajo'
    _order = 'sequence, id'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    workcenter_id = fields.Many2one(
        comodel_name='mrp.workcenter',
        string='Centro de trabajo',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='workcenter_id.company_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Producto',
        required=True,
        check_company=True,
        domain="[('type', '=', 'consu'), ('tracking', '=', 'none')]",
    )
    product_uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='Unidad de medida',
        related='product_id.uom_id',
        readonly=True,
    )
    qty_per_unit = fields.Float(
        string='Cantidad por unidad producida',
        digits='Product Unit of Measure',
        default=0.0,
    )
    qty_fixed = fields.Float(
        string='Cantidad fija por orden de trabajo',
        digits='Product Unit of Measure',
        default=0.0,
    )

    _sql_constraints = [
        (
            'workcenter_product_uniq',
            'unique(workcenter_id, product_id)',
            'Un producto solo puede figurar una vez como consumible del mismo centro de trabajo.',
        ),
    ]

    @api.constrains('qty_per_unit', 'qty_fixed')
    def _check_qty(self):
        for rec in self:
            if rec.qty_per_unit < 0 or rec.qty_fixed < 0:
                raise ValidationError(_('Las cantidades de un consumible no pueden ser negativas.'))
            if not rec.qty_per_unit and not rec.qty_fixed:
                raise ValidationError(_(
                    "El consumible '%(product)s' necesita una cantidad por unidad producida "
                    "o una cantidad fija.",
                    product=rec.product_id.display_name,
                ))

    @api.constrains('product_id')
    def _check_product(self):
        for rec in self:
            if not rec.product_id:
                continue
            if rec.product_id.type != 'consu':
                raise ValidationError(_(
                    "El consumible '%(product)s' debe ser un producto de tipo Bienes: "
                    "los servicios y combos no generan movimientos de stock.",
                    product=rec.product_id.display_name,
                ))
            if rec.product_id.tracking != 'none':
                raise ValidationError(_(
                    "El consumible '%(product)s' se controla por lote o serie. Los consumibles "
                    "se consumen automáticamente, así que no pueden llevar seguimiento.",
                    product=rec.product_id.display_name,
                ))

    def _get_qty_to_consume(self, workorder):
        """Cantidad a consumir en la unidad de medida del producto."""
        self.ensure_one()
        produced_qty = workorder._woec_get_produced_qty()
        return (produced_qty * self.qty_per_unit) + self.qty_fixed
