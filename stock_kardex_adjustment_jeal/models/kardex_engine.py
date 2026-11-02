# -*- coding: utf-8 -*-
"""Motor del kardex valorizado con ajustes línea por línea.

No depende del ORM: recibe los eventos (capas de valoración, apuntes manuales
y facturas de proveedor) de todos los productos y devuelve las filas del
kardex de cada producto y los ajustes que hay que registrar. Así se puede
probar con datos sueltos; el modelo solo lee la base y registra el resultado.

Recorre todos los productos juntos en orden de fecha contable, porque un
producto puede depender de otro el mismo día (fabricaciones y desmontajes).

Reglas (notas técnicas Kardex Connected):

* Antes del período el saldo es la suma de los valores de Odoo (capas y
  apuntes manuales incluidos); no se recalcula nada.
* En el período, cada salida se muestra al costo de Odoo y debajo va un ajuste
  al promedio vigente (saldo valorizado / saldo en cantidad, con todos los
  ajustes previos). Con saldo negativo o en cero se usa el último costo
  promedio positivo y la línea queda marcada para revisión (R10).
* Devoluciones de clientes: al costo recalculado de la salida de origen
  (``origin``) o al promedio vigente (``current``).
* Devoluciones a proveedor: al costo unitario de la recepción de origen, con
  todas sus capas (R1). Reingresos: al valor con que salió la devolución que
  revierten (R2).
* Facturas de proveedor: por cada factura, lo facturado de la línea de compra
  contra lo ya registrado (recepciones, devoluciones, diferencias de precio de
  Odoo, costos en destino y ajustes), en la fecha de la factura y sobre la
  recepción que quedó en el almacén, separado en cambio y precio (R3 a R6).
* Fabricaciones: los ajustes de los consumos pasan al producto fabricado de la
  misma orden (R8). Desmontajes de una orden: los componentes vuelven por el
  valor con que sale el producto, repartido según su costo en la orden (R9).
"""
from collections import deque
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal('0')
CENT = Decimal('0.01')
QTY_EPS = Decimal('0.0001')
# Diferencia de redondeo aceptada entre cantidad facturada y recibida
# (facturas con tres decimales contra recepciones con dos): 0.1 %
QTY_TOLERANCE = Decimal('0.001')

# Orden dentro del mismo día (R11): primero las entradas, luego la cadena de
# producción en el orden en que se hizo (cada orden consume antes de producir
# y cada desmontaje saca el producto antes de devolver los componentes) y al
# final las demás salidas.
GROUP_MANUAL = 0
GROUP_IN = 1
GROUP_IN_VALUE = GROUP_IN  # compatibilidad
GROUP_PRODUCTION = 2
GROUP_OUT = 3
GROUP_OTHER = GROUP_OUT  # compatibilidad

ROW_OPENING = 'opening'
ROW_LAYER = 'layer'
ROW_MANUAL = 'manual'
ROW_ADJ_COST = 'adj_cost'
ROW_ADJ_FX = 'adj_fx'
ROW_ADJ_PRICE = 'adj_price'
ROW_ADJ_PROD = 'adj_prod'
ADJUSTMENT_ROWS = (ROW_ADJ_COST, ROW_ADJ_FX, ROW_ADJ_PRICE, ROW_ADJ_PROD)

ADJ_COST = 'cost'
ADJ_RETURN = 'return'
ADJ_FX = 'fx'
ADJ_PRICE = 'price'
ADJ_PROD = 'production'
ROW_OF_ADJ = {
    ADJ_COST: ROW_ADJ_COST,
    ADJ_RETURN: ROW_ADJ_COST,
    ADJ_FX: ROW_ADJ_FX,
    ADJ_PRICE: ROW_ADJ_PRICE,
    ADJ_PROD: ROW_ADJ_PROD,
}
INVOICE_ADJUSTMENTS = (ADJ_FX, ADJ_PRICE)

# Papel de cada capa en su movimiento
ROLE_IN = 'in'
ROLE_OUT = 'out'
ROLE_CUSTOMER_RETURN = 'customer_return'
ROLE_VENDOR_RETURN = 'vendor_return'
ROLE_REENTRY = 'reentry'
ROLE_MO_CONSUME = 'mo_consume'
ROLE_MO_PRODUCE = 'mo_produce'
ROLE_UB_OUT = 'ub_out'
ROLE_UB_IN = 'ub_in'

# Marcas de revisión
REVIEW_NEGATIVE = 'negative_stock'
REVIEW_PURCHASE = 'purchase'
REVIEW_PRODUCTION = 'production'


def to_decimal(value):
    if value is None or value is False:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value):
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def event_sort_key(event):
    seq = event['seq']
    return (event['date'], event['group'], seq if isinstance(seq, tuple) else (seq,))


class _ProductState:
    __slots__ = ('qty', 'value', 'raw', 'last_unit', 'rows', 'adjustments', 'opening', 'negatives',
                 'last_out')

    def __init__(self):
        self.qty = self.value = self.raw = ZERO
        self.last_unit = None
        self.rows = []
        self.adjustments = []
        self.opening = None
        # Salidas tomadas con stock negativo, de la más antigua a la más nueva:
        # [evento, cantidad sin cubrir, costo unitario, se regulariza]
        self.negatives = deque()
        # Última salida al promedio (antes del período), para regularizar un
        # saldo inicial negativo
        self.last_out = None

    def remember_unit(self):
        if self.qty > 0 and self.value > 0:
            self.last_unit = self.value / self.qty


class _PurchaseState:
    """Lo registrado y lo facturado de una línea de compra (R3)."""
    __slots__ = ('registered', 'price_diff', 'adjusted', 'net_qty', 'inv_value',
                 'inv_qty', 'base_qty', 'base_value', 'incoming', 'remaining', 'pending',
                 'pd_announced', 'pd_registered', 'last_invoice', 'landed')

    def __init__(self):
        self.registered = self.price_diff = self.adjusted = ZERO
        self.net_qty = self.inv_value = self.inv_qty = ZERO
        self.base_qty = self.base_value = ZERO
        # Recepciones y reingresos en el orden del kardex
        self.incoming = []
        # Cantidad de cada recepción o reingreso que sigue en el almacén
        self.remaining = {}
        # Facturas con más cantidad que la recibida hasta su fecha: se ajustan
        # cuando llega la recepción (con la fecha de la recepción)
        self.pending = []
        # Diferencias de precio que Odoo generó desde cada factura: las
        # anunciadas por la factura y las que ya pasaron por el kardex (su
        # asiento puede tener una fecha posterior a la factura).
        self.pd_announced = {}
        self.pd_registered = {}
        self.last_invoice = None
        # Costos en destino de las recepciones de la compra
        self.landed = ZERO

    def pending_price_diff(self):
        return sum((value - self.pd_registered.get(invoice, ZERO)
                    for invoice, value in self.pd_announced.items()), ZERO)

    def covered(self):
        return self.inv_qty <= self.net_qty + max(QTY_EPS, abs(self.net_qty) * QTY_TOLERANCE)

    def anchor(self):
        """Recepción (o reingreso) que quedó en el almacén: la última con
        cantidad sin devolver (R4)."""
        for event in reversed(self.incoming):
            if self.remaining.get(event.get('stock_move_id'), ZERO) > QTY_EPS:
                return event
        return self.incoming[-1] if self.incoming else None


class KardexEngine:
    """Recorre los eventos y arma el kardex de cada producto.

    Eventos (``dict``):

    * ``kind``: ``'layer'``, ``'manual'`` o ``'invoice'``.
    * ``product``: producto (por defecto 0).
    * ``date``: fecha contable; ``group`` y ``seq``: orden dentro del día.
    * ``qty`` y ``value``: cantidad y valor de Odoo.
    * ``layer_id`` (por defecto ``seq``) y ``stock_move_id``.
    * ``role``: papel de la capa (``ROLE_*``); por defecto entrada o salida
      según el signo de la cantidad.
    * ``origin_move_id``: movimiento que revierte (devoluciones y reingresos);
      ``origin_origin_move_id``: recepción de origen de la devolución que
      revierte un reingreso.
    * ``pol``: línea de compra; ``price_diff``: capa de diferencia de precio de
      una factura; ``adj_type``: tipo de un ajuste de kardex ya registrado.
    * ``mo_finished``: en consumos y producciones de una orden, las capas del
      producto fabricado: ``{layer_id: (producto, movimiento, valor, info)}``.
    * ``ub_components``: en la salida de un desmontaje de una orden, los
      componentes que vuelven: lista de ``{'layers': {layer_id: cantidad},
      'qty': cantidad, 'raw_moves': [consumos en la orden], 'odoo_value': valor}``.
    * Facturas: ``pol``, ``invoice_id``, ``qty`` y ``value`` (en soles, con
      signo), ``amount_currency``, ``foreign`` y ``po_price`` (precio de la
      orden en moneda extranjera por unidad del producto).
    * ``info``: datos de presentación; el motor no los toca.
    """

    def __init__(self, date_from, date_to, return_cost_method='origin',
                 origin_units=None, fx_threshold=ZERO):
        self.date_from = date_from
        self.date_to = date_to
        self.return_cost_method = return_cost_method
        # Costo unitario de salidas de origen sin capas leídas
        self.origin_units = origin_units or {}
        self.fx_threshold = to_decimal(fx_threshold)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def run(self, events):
        """Un solo producto: devuelve su resultado."""
        results = self.run_all(events)['products']
        if results:
            return next(iter(results.values()))
        return self._result(_ProductState())

    def run_all(self, events):
        self._products = {}
        self._moves = {}         # {movimiento: [cantidad, valor con ajustes]}
        self._purchases = {}     # {línea de compra: _PurchaseState}
        self._processed = set()  # capas ya recorridas
        self._mo_pending = {}    # {capa fabricada: importe por transferir}
        self._ub_targets = {}    # {capa de componente: valor objetivo}
        self.warnings = []
        events = sorted(
            (e for e in events if e['date'] <= self.date_to), key=event_sort_key)
        for event in events:
            if event['date'] < self.date_from:
                self._apply_before(event)
        for state in self._products.values():
            self._open(state)
            if state.qty < -QTY_EPS and state.last_out:
                # Saldo inicial negativo: la primera entrada del período lo
                # regulariza a su costo, como las salidas negativas del período
                unit = state.value / state.qty if state.value < 0 else (state.last_unit or ZERO)
                state.negatives.append([state.last_out, -state.qty, unit, bool(unit)])
        for event in events:
            if event['date'] < self.date_from:
                continue
            state = self._state(event.get('product', 0))
            if event['kind'] == 'invoice':
                self._invoice(event, in_period=True)
            elif event['kind'] == 'manual':
                self._manual(event, state)
            else:
                self._layer(event, state)
        for ps in self._purchases.values():
            if ps.pending:
                self._review(REVIEW_PURCHASE, ps.pending[-1], 'Facturado (%s) mayor que recibido (%s): no se ajusta' % (
                    '{:f}'.format(ps.inv_qty.normalize()), '{:f}'.format(ps.net_qty.normalize())))
        return {
            'products': {pid: self._result(state) for pid, state in self._products.items()},
            'warnings': self.warnings,
        }

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    def _state(self, product, opened=True):
        state = self._products.get(product)
        if state is None:
            state = self._products[product] = _ProductState()
            if opened:
                self._open(state)
        return state

    def _open(self, state):
        if state.opening is not None:
            return
        state.opening = {
            'kind': ROW_OPENING,
            'date': self.date_from,
            'bal_qty': state.qty,
            'bal_value': state.value,
            'raw_bal_value': state.raw,
        }
        state.rows.insert(0, state.opening)

    def _result(self, state):
        self._open(state)
        return {
            'opening_qty': state.opening['bal_qty'],
            'opening_value': state.opening['bal_value'],
            'closing_qty': state.qty,
            'closing_value': state.value,
            'raw_closing_value': state.raw,
            'rows': state.rows,
            'adjustments': state.adjustments,
        }

    def _role(self, event):
        role = event.get('role')
        if role:
            return role
        if event.get('customer_return_origin_id'):
            return ROLE_CUSTOMER_RETURN
        return ROLE_IN if to_decimal(event['qty']) >= 0 else ROLE_OUT

    @staticmethod
    def _origin(event):
        return event.get('origin_move_id') or event.get('customer_return_origin_id')

    def _move_unit(self, move_id):
        data = self._moves.get(move_id)
        if not data or not data[0]:
            return None
        return data[1] / data[0]

    def _register(self, event, qty, value, role, adj_type=None):
        """Acumula una capa o un ajuste en su movimiento y en su compra."""
        move_id = event.get('stock_move_id')
        if move_id:
            data = self._moves.setdefault(move_id, [ZERO, ZERO])
            data[0] += qty
            data[1] += value
        pol = event.get('pol')
        if not pol:
            return
        ps = self._purchases.setdefault(pol, _PurchaseState())
        if event.get('landed') and not adj_type:
            ps.landed += value
            return
        ps.registered += value
        ps.net_qty += qty
        if event.get('price_diff') and not adj_type:
            ps.price_diff += value
            invoice = event.get('price_diff_invoice_id') or event.get('invoice_id')
            if invoice:
                ps.pd_registered[invoice] = ps.pd_registered.get(invoice, ZERO) + value
        if adj_type in INVOICE_ADJUSTMENTS:
            ps.adjusted += value
        if qty > 0 and role in (ROLE_IN, ROLE_REENTRY):
            ps.incoming.append(event)
            ps.remaining[move_id] = ps.remaining.get(move_id, ZERO) + qty
            if role == ROLE_IN:
                ps.base_qty += qty
                ps.base_value += value
        elif qty < 0 and role == ROLE_VENDOR_RETURN:
            origin = self._origin(event)
            if origin in ps.remaining:
                ps.remaining[origin] += qty

    def _apply_before(self, event):
        """Antes del período: valores de Odoo sin recalcular."""
        if event['kind'] == 'invoice':
            self._invoice(event, in_period=False)
            return
        state = self._state(event.get('product', 0), opened=False)
        qty = to_decimal(event['qty'])
        value = money(event['value'])
        state.qty += qty
        state.value += value
        state.raw += value
        state.remember_unit()
        if event['kind'] == 'layer':
            if qty < 0 and self._role(event) in (ROLE_OUT, ROLE_MO_CONSUME):
                state.last_out = event
            self._register(event, qty, value, self._role(event), event.get('adj_type'))
            self._processed.add(event.get('layer_id', event['seq']))
            ps = self._purchases.get(event.get('pol'))
            if ps and ps.pending and qty > 0 and ps.covered():
                ps.pending = []

    # ------------------------------------------------------------------
    # Filas
    # ------------------------------------------------------------------
    @staticmethod
    def _join(note, extra):
        return '%s; %s' % (note, extra) if note else extra

    @staticmethod
    def _row(event, kind, qty, value, bal_qty, bal_value, raw_bal_value):
        row = {
            'kind': kind,
            'event': event,
            'date': event['date'],
            'in_qty': ZERO, 'in_value': ZERO,
            'out_qty': ZERO, 'out_value': ZERO,
            'bal_qty': bal_qty,
            'bal_value': bal_value,
            'raw_bal_value': raw_bal_value,
            'adjust': ZERO,
            'note': '',
        }
        if kind != ROW_LAYER or not qty:
            # Líneas de solo valor: + en Entrada, - en Salida sin signo
            if value >= 0:
                row['in_value'] = value
            else:
                row['out_value'] = -value
        elif qty >= 0:
            row['in_qty'] = qty
            row['in_value'] = value
        else:
            row['out_qty'] = -qty
            row['out_value'] = -value
        return row

    def _review(self, kind, event, text, product=None):
        self.warnings.append({
            'type': kind,
            'product': event.get('product', 0) if product is None else product,
            'date': event['date'],
            'info': event.get('info') or {},
            'text': text,
        })

    def _emit(self, state, event, adj_type, amount, date=None, recalc=None,
              note='', review=None, extra=None):
        """Agrega una línea de ajuste debajo de ``event`` y la registra."""
        amount = money(amount)
        if not amount:
            return None
        extra = extra or {}
        state.value += amount
        row = self._row(dict(event, date=date or event['date']), ROW_OF_ADJ[adj_type],
                        ZERO, amount, state.qty, state.value, state.raw)
        row.update(adjust=amount, recalc=recalc, note=note, adj_type=adj_type)
        if review:
            row['review'] = review
        row.update(extra)
        state.rows.append(row)
        state.adjustments.append({
            'type': adj_type,
            'layer_id': event.get('layer_id', event.get('seq')),
            'stock_move_id': event.get('stock_move_id'),
            'date': row['date'],
            'amount': amount,
            'info': event.get('info') or {},
            'invoice_id': extra.get('invoice_id'),
        })
        self._register(event, ZERO, amount, self._role(event), adj_type)
        state.remember_unit()
        return row

    # ------------------------------------------------------------------
    # Eventos del período
    # ------------------------------------------------------------------
    def _manual(self, event, state):
        value = money(event['value'])
        state.value += value
        state.raw += value
        state.rows.append(self._row(event, ROW_MANUAL, ZERO, value, state.qty, state.value, state.raw))
        state.remember_unit()

    @staticmethod
    def _out_recalc(state, out_qty, odoo_cost):
        """Costo de una salida al promedio vigente; con saldo negativo, en cero
        o con valor negativo, al último costo promedio positivo (R10)."""
        qty, value = state.qty, state.value
        if qty > 0 and value > 0:
            if out_qty == qty:
                return value, '', None
            if out_qty > qty:
                return (money(out_qty * value / qty),
                        'Sale más que el saldo: al promedio vigente', REVIEW_NEGATIVE)
            return money(out_qty * value / qty), '', None
        if state.last_unit:
            return (money(out_qty * state.last_unit),
                    'Stock negativo o sin saldo: al último costo promedio positivo',
                    REVIEW_NEGATIVE)
        return odoo_cost, 'Sin saldo previo: se mantiene el costo de Odoo', None

    def _layer(self, event, state):
        layer_id = event.get('layer_id', event['seq'])
        role = self._role(event)
        ev_qty = to_decimal(event['qty'])
        ev_value = money(event['value'])
        note = event.get('note') or ''
        recalc = None
        adj_type = None
        review = None
        adjust = ZERO

        qty_before = state.qty
        if ev_qty < 0:
            out_qty = -ev_qty
            odoo_cost = -ev_value
            if role == ROLE_VENDOR_RETURN and qty_before > 0 and out_qty >= qty_before:
                # La devolución deja el producto sin saldo: se lleva todo el valor
                recalc = state.value if out_qty == qty_before else money(out_qty * state.value / qty_before)
                adj_type = ADJ_RETURN
                note = self._join(note, 'Devolución que deja el producto sin saldo')
            elif role == ROLE_UB_OUT and event.get('ub_components'):
                recalc = self._unbuild_targets(event)
                adj_type = ADJ_PROD
                note = self._join(note, 'Desmontaje al costo de la orden')
            elif role == ROLE_VENDOR_RETURN:
                unit = self._move_unit(self._origin(event))
                if unit is not None and unit > 0:
                    recalc = money(out_qty * unit)
                    adj_type = ADJ_RETURN
                    note = self._join(note, 'Devolución al costo de la recepción de origen')
            if recalc is None:
                recalc, extra_note, review = self._out_recalc(state, out_qty, odoo_cost)
                if extra_note:
                    note = self._join(note, extra_note)
                adj_type = ADJ_COST
            adjust = odoo_cost - recalc
            beyond = out_qty - max(qty_before, ZERO)
            if beyond > QTY_EPS:
                # Las salidas al promedio se regularizan al costo de la entrada
                # que cubre el negativo, como hace Odoo (vacuum)
                state.negatives.append([event, beyond, recalc / out_qty if out_qty else ZERO,
                                        adj_type == ADJ_COST and role in (ROLE_OUT, ROLE_MO_CONSUME)])
        elif ev_qty > 0:
            if role == ROLE_CUSTOMER_RETURN:
                unit = None
                if self.return_cost_method == 'origin':
                    origin = self._origin(event)
                    unit = self._move_unit(origin)
                    if unit is None and origin in self.origin_units:
                        unit = to_decimal(self.origin_units[origin])
                if unit is None and state.qty > 0 and state.value > 0:
                    unit = state.value / state.qty
                if unit is None:
                    note = self._join(note, 'Sin costo de origen ni saldo previo')
                else:
                    recalc = money(ev_qty * unit)
                    adj_type = ADJ_COST
                    adjust = recalc - ev_value
            elif role == ROLE_REENTRY:
                unit = self._reentry_unit(event)
                if unit is not None and unit > 0:
                    recalc = money(ev_qty * unit)
                    adj_type = ADJ_RETURN
                    adjust = recalc - ev_value
                    note = self._join(note, 'Reingreso al valor de la devolución')
            elif role == ROLE_UB_IN and layer_id in self._ub_targets:
                recalc = self._ub_targets.pop(layer_id)
                adj_type = ADJ_PROD
                adjust = recalc - ev_value
                note = self._join(note, 'Componente al valor del producto desmontado')

        state.qty += ev_qty
        state.value += ev_value
        state.raw += ev_value
        row = self._row(event, ROW_LAYER, ev_qty, ev_value, state.qty, state.value, state.raw)
        row['note'] = note
        if recalc is not None:
            row['recalc'] = recalc
        if review:
            row['review'] = review
            self._review(review, event, note)
        state.rows.append(row)
        self._register(event, ev_qty, ev_value, role, event.get('adj_type'))
        self._processed.add(layer_id)
        state.remember_unit()

        adjust = money(adjust)
        layer_adjust = ZERO
        if adjust and adj_type:
            self._emit(state, event, adj_type, adjust, recalc=recalc, review=review)
            layer_adjust += adjust

        ps = self._purchases.get(event.get('pol')) if event.get('pol') else None
        if ps and ev_qty > 0 and role in (ROLE_IN, ROLE_REENTRY) and ps.pending and ps.covered():
            trigger = ps.pending[-1]
            names = ', '.join(filter(None, (
                (p.get('info') or {}).get('invoices') for p in ps.pending)))
            ps.pending = []
            self._adjust_invoice(ps, dict(trigger, info=dict(trigger.get('info') or {}, invoices=names)),
                                 event['date'])
        elif ps and ev_qty and ps.last_invoice and not ps.pending:
            # Recepción, devolución o reingreso después de facturar: la compra
            # se vuelve a cuadrar con lo facturado (60 + 61 = 0, R3)
            self._adjust_invoice(ps, ps.last_invoice, event['date'], note='Regularización de la compra')
        elif ps and not ev_qty and ps.last_invoice and event.get('landed') and not ps.pending:
            # Costo en destino después de facturar: cubre la diferencia de la
            # factura ya ajustada (R3)
            self._adjust_invoice(ps, ps.last_invoice, event['date'], note='Costo en destino de la compra')

        if role == ROLE_MO_CONSUME and adjust:
            self._transfer_to_finished(event, -adjust)
        elif role == ROLE_MO_PRODUCE:
            pending = self._mo_pending.pop(layer_id, ZERO)
            if pending:
                self._emit(state, event, ADJ_PROD, pending,
                           note='Ajustes de los consumos de la orden')
                layer_adjust += money(pending)

        if ev_qty > 0 and state.negatives:
            self._cover_negatives(state, event, ev_qty, (ev_value + layer_adjust) / ev_qty)

    def _cover_negatives(self, state, event, in_qty, in_unit):
        """La entrada cubre primero las salidas tomadas con stock negativo; las
        que se valorizaron al promedio pasan al costo de esta entrada (como el
        vacuum de Odoo). El ajuste va debajo de cada salida, con su
        contrapartida, y el de un consumo pasa al fabricado (R8)."""
        left = in_qty
        while left > QTY_EPS and state.negatives:
            entry = state.negatives[0]
            out_event, pending_qty, unit, revalue = entry
            covered = min(pending_qty, left)
            left -= covered
            entry[1] -= covered
            if entry[1] <= QTY_EPS:
                state.negatives.popleft()
            if not revalue:
                continue
            correction = money(covered * (unit - in_unit))
            if not correction:
                continue
            out_state = self._state(out_event.get('product', 0))
            self._emit(out_state, out_event, ADJ_COST, correction, date=event['date'],
                       note='Salida con stock negativo al costo de la entrada %s' % (
                           (event.get('info') or {}).get('reference') or ''))
            if self._role(out_event) == ROLE_MO_CONSUME:
                self._transfer_to_finished(dict(out_event, date=event['date']), -correction)

    def _reentry_unit(self, event):
        """Costo unitario de la devolución que revierte el reingreso (R2): la
        devolución ya recalculada o, si su fecha es posterior, el costo de su
        recepción de origen, que es como saldrá (R1)."""
        unit = self._move_unit(self._origin(event))
        if unit is not None and unit > 0:
            return unit
        origin_origin = event.get('origin_origin_move_id')
        if origin_origin:
            unit = self._move_unit(origin_origin)
            if unit is not None and unit > 0:
                return unit
        return None

    # ------------------------------------------------------------------
    # Fabricaciones y desmontajes (R8, R9)
    # ------------------------------------------------------------------
    def _transfer_to_finished(self, event, amount):
        """El ajuste de un consumo pasa al producto fabricado de la orden,
        repartido según el valor de Odoo de cada capa fabricada."""
        finished = event.get('mo_finished') or {}
        if not finished:
            self._review(REVIEW_PRODUCTION, event,
                         'Consumo sin producto fabricado: el ajuste queda en la cuenta de producción')
            return
        total = sum(to_decimal(f[2]) for f in finished.values())
        layers = sorted(finished)
        left = amount
        for index, layer_id in enumerate(layers):
            product, move_id, value, info = finished[layer_id]
            if index == len(layers) - 1:
                part = left
            elif total:
                part = money(amount * to_decimal(value) / total)
            else:
                part = money(amount / len(layers))
            left -= part
            if not part:
                continue
            if layer_id in self._processed:
                # El fabricado ya pasó: el ajuste va debajo de él con la fecha
                # del consumo
                target = {
                    'kind': 'layer', 'product': product, 'date': event['date'],
                    'group': event['group'], 'seq': event['seq'],
                    'layer_id': layer_id, 'stock_move_id': move_id,
                    'role': ROLE_MO_PRODUCE, 'info': info or {},
                }
                self._emit(self._state(product), target, ADJ_PROD, part,
                           note='Ajuste de consumo de la orden')
            else:
                self._mo_pending[layer_id] = self._mo_pending.get(layer_id, ZERO) + part

    def _unbuild_targets(self, event):
        """Desmontaje de una orden (R9): cada componente vuelve a su costo de
        consumo en la orden (con sus ajustes) por la cantidad devuelta, y el
        producto sale por la suma; así el desmontaje es neutro y no depende del
        saldo del producto. Devuelve el valor de salida del producto."""
        components = event.get('ub_components') or []
        total = ZERO
        for comp in components:
            raw = [self._moves.get(m) for m in comp.get('raw_moves') or []]
            raw_qty = sum(r[0] for r in raw if r)
            raw_value = sum(r[1] for r in raw if r)
            unit = raw_value / raw_qty if raw_qty else None
            comp_qty = to_decimal(comp['qty'])
            for layer_id, qty in sorted(comp['layers'].items()):
                if unit is not None and unit > 0:
                    target = money(to_decimal(qty) * unit)
                else:
                    share = to_decimal(qty) / comp_qty if comp_qty else ZERO
                    target = money(to_decimal(comp.get('odoo_value')) * share)
                self._ub_targets[layer_id] = target
                total += target
        return total

    # ------------------------------------------------------------------
    # Facturas de proveedor (R3 a R6)
    # ------------------------------------------------------------------
    def _invoice(self, event, in_period):
        ps = self._purchases.setdefault(event['pol'], _PurchaseState())
        ps.inv_qty += to_decimal(event['qty'])
        ps.inv_value += money(event['value'])
        if event.get('price_diff_value') and event.get('invoice_id'):
            ps.pd_announced[event['invoice_id']] = (
                ps.pd_announced.get(event['invoice_id'], ZERO) + money(event['price_diff_value']))
        if not ps.covered():
            # Facturado antes de recibir (o más de lo recibido): se ajusta
            # cuando llegue la recepción; si no llega, queda para revisión.
            ps.pending.append(event)
            return
        ps.pending = []
        ps.last_invoice = event
        if in_period:
            self._adjust_invoice(ps, event, event['date'])

    def _adjust_invoice(self, ps, event, date, note=None):
        """Ajuste de la factura: lo facturado acumulado de la línea de compra
        menos lo ya registrado de la cantidad facturada (R3), sobre la
        recepción que quedó en el almacén (R4), separado en cambio y precio
        (R6)."""
        if ps.net_qty <= QTY_EPS:
            self._review(REVIEW_PURCHASE, event, 'Factura sin cantidad recibida: no se ajusta')
            return
        qty = to_decimal(event['qty'])
        value = money(event['value'])
        ratio = min(ps.inv_qty / ps.net_qty, Decimal('1'))
        # Lo que Odoo ya llevó por diferencia de precio de las facturas, aunque
        # su capa todavía no haya pasado por el kardex (R3)
        price_diff = ps.price_diff + ps.pending_price_diff()
        base = ps.registered - ps.adjusted - ps.price_diff
        # Diferencia entre lo facturado y lo registrado de la cantidad facturada,
        # sin los ajustes de factura del kardex
        gap = ps.inv_value - base * ratio - price_diff
        if gap > 0:
            # Los costos en destino cubren la diferencia; si son mayores
            # (fletes, servicios), el exceso se queda en el inventario
            gap = max(gap - ps.landed * ratio, ZERO)
        adjust = money(gap - ps.adjusted)
        if not adjust or abs(adjust) < self.fx_threshold:
            return
        anchor = ps.anchor()
        if not anchor:
            self._review(REVIEW_PURCHASE, event, 'Factura sin recepción en el kardex: no se ajusta')
            return
        fx_part = ZERO
        tc_invoice = tc_receipt = None
        amount_currency = to_decimal(event.get('amount_currency'))
        po_price = to_decimal(event.get('po_price'))
        if event.get('foreign') and amount_currency and po_price and ps.base_qty:
            receipt_unit = ps.base_value / ps.base_qty
            tc_receipt = receipt_unit / po_price
            tc_invoice = value / amount_currency
            theoretical = value - qty * receipt_unit
            fx_full = qty * po_price * (tc_invoice - tc_receipt)
            if theoretical:
                fx_part = money(adjust * fx_full / theoretical)
        price_part = adjust - fx_part
        # Diferencias de redondeo entre cambio y precio: van a la otra parte
        tolerance = max(self.fx_threshold, Decimal('1.00'))
        if fx_part and price_part and abs(price_part) < tolerance:
            fx_part, price_part = adjust, ZERO
        elif fx_part and price_part and abs(fx_part) < tolerance:
            fx_part, price_part = ZERO, adjust
        state = self._state(anchor.get('product', 0))
        target = dict(anchor, info=dict(anchor.get('info') or {}, **(event.get('info') or {})))
        extra = {
            'invoice_id': event.get('invoice_id'),
            'tc_invoice': tc_invoice,
            'tc_receipt': tc_receipt,
        }
        if fx_part:
            self._emit(state, target, ADJ_FX, fx_part, date=date,
                       note=note or 'Diferencia de cambio', extra=extra)
        if price_part:
            self._emit(state, target, ADJ_PRICE, price_part, date=date,
                       note=note or 'Diferencia de precio', extra=extra)
