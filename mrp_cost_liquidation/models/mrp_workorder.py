from odoo import models


class MRPWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def _cal_cost(self, date=False):
        """Cálculo de costo total de una WO sumando 4 componentes:

          1. Servicios:   workcenter.costs_hour * total_hours       (upstream)
          2. Mano obra:   workcenter.employee_costs_hour * total_hours   (flat)
          3. Depreciación: workcenter.depreciation_costs_hour * total_hours
          4. Otros:       workcenter.other_costs_hour * total_hours

        Decisión funcional del cliente: en v16 (y se preserva en v18) la
        mano de obra se computa con la tarifa plana del workcenter, NO con
        la tarifa por empleado de cada time entry. Por eso restamos la
        contribución per-employee que ya añade enterprise y la sustituimos
        por la tarifa plana del workcenter.

        Compatibilidad Odoo 18 (cambio crítico de firma):
            * v16 base:   `_cal_cost(self, times=None)` (recibía recordset)
            * v18 base:   `_cal_cost(self, date=False)` (recibe fecha tope)
            * v18 enterprise (mrp_workorder): `_cal_cost(date)` = super +
              sum(time_ids.total_cost) filtrando por `date` si se pasa.

        Verificado en:
            * odoo/addons/mrp/models/mrp_workorder.py:589
            * repos_dev/enterprise/mrp_workorder/models/mrp_workorder.py:854
        """
        self.ensure_one()

        res = super()._cal_cost(date=date)

        # Filtrar time_ids igual que lo hace v18 enterprise upstream.
        times = self.time_ids
        if date:
            times = times.filtered(lambda t: t.date_end and t.date_end <= date)

        # Restar la contribución per-empleado que añade enterprise.
        # `total_cost` viene de mrp_workorder enterprise (mrp_workcenter.py:62):
        #   total_cost = employee_cost * duration / 60
        if times and 'total_cost' in times._fields:
            res -= sum(times.mapped('total_cost'))

        # Sustituir por la mano de obra plana del workcenter.
        minutes = self.duration or 0.0
        hours = minutes / 60.0 if minutes else 0.0
        labor_hour = self.workcenter_id.employee_costs_hour or 0.0
        res += labor_hour * hours

        # Añadir depreciación + otros (nuestros campos extra computados
        # en mrp.workcenter.productivity).
        if times and 'extra_total_cost' in times._fields:
            res += sum(times.mapped('extra_total_cost'))

        return res
