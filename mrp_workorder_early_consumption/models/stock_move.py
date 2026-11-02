# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    wo_auto_consumable = fields.Boolean(
        string='Consumible automático de OT',
        default=False,
        index=True,
        copy=False,
        readonly=True,
        help='Movimiento generado automáticamente al terminar la orden de trabajo, '
             'a partir de los consumibles del centro de trabajo.',
    )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _woec_get_workcenter_analytic_distribution(self):
        """Distribución analítica del centro de trabajo de la orden de
        trabajo del movimiento, o False si no tiene."""
        self.ensure_one()
        workcenter = self.workorder_id.workcenter_id
        if workcenter and workcenter.analytic_distribution:
            return dict(workcenter.analytic_distribution)
        return False

    def _woec_is_raw_consumption_move(self):
        self.ensure_one()
        return bool(
            self.raw_material_production_id
            and self.location_dest_id.usage == 'production'
        )

    # -------------------------------------------------------------------------
    # Overrides
    # -------------------------------------------------------------------------
    def _get_analytic_distribution(self):
        if self.workorder_id and self._woec_is_raw_consumption_move():
            dist = self._woec_get_workcenter_analytic_distribution()
            if dist:
                return dist
        return super()._get_analytic_distribution()

    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, *args, **kwargs):
        """Pone la analítica del centro de trabajo en la línea al debe del
        asiento de valoración del consumo."""
        self.ensure_one()
        move_lines = super()._prepare_account_move_line(
            qty, cost, credit_account_id, debit_account_id, *args, **kwargs
        )
        if not (self.workorder_id and self._woec_is_raw_consumption_move()):
            return move_lines
        dist = self._woec_get_workcenter_analytic_distribution()
        if not dist:
            return move_lines

        for line in move_lines or []:
            if isinstance(line, dict):
                vals = line
            elif isinstance(line, (list, tuple)) and len(line) == 3 and isinstance(line[2], dict):
                vals = line[2]
            else:
                continue
            if vals.get('analytic_distribution') or vals.get('account_id') != debit_account_id:
                continue
            balance = vals.get('balance')
            if balance is None:
                balance = float(vals.get('debit') or 0.0) - float(vals.get('credit') or 0.0)
            if balance > 0:
                vals['analytic_distribution'] = dist
        return move_lines

    def _ignore_automatic_valuation(self):
        self.ensure_one()
        if self.env.context.get('woec_force_valuation') and self.raw_material_production_id:
            return False
        return super()._ignore_automatic_valuation()
