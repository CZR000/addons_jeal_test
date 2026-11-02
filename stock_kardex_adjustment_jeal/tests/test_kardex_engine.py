# -*- coding: utf-8 -*-
from datetime import date
from decimal import Decimal as D

from odoo.tests import BaseCase, tagged

from ..models.kardex_engine import (
    ADJ_COST, ADJ_FX, ADJ_PRICE, ADJ_PROD, ADJ_RETURN, GROUP_IN, GROUP_MANUAL,
    GROUP_OUT, GROUP_PRODUCTION, REVIEW_NEGATIVE, REVIEW_PURCHASE, ROLE_MO_CONSUME,
    ROLE_MO_PRODUCE, ROLE_REENTRY, ROLE_UB_IN, ROLE_UB_OUT, ROLE_VENDOR_RETURN,
    ROW_ADJ_COST, ROW_ADJ_FX, ROW_ADJ_PRICE, ROW_ADJ_PROD, ROW_LAYER, ROW_MANUAL,
    ROW_OPENING, KardexEngine,
)

DF = date(2026, 1, 1)
DT = date(2026, 1, 31)


def ev(layer_id, day, qty, value, group=None, kind='layer', month=1, **extra):
    """Capa de prueba: ``layer_id`` es también el desempate salvo que se pase
    ``seq`` (la cadena de producción usa tuplas)."""
    if group is None:
        group = GROUP_IN if qty >= 0 else GROUP_OUT
    if kind == 'manual':
        group = GROUP_MANUAL
    event = {
        'kind': kind, 'seq': (0, layer_id), 'layer_id': layer_id,
        'date': date(2026 if month else 2025, month or 12, day),
        'group': group, 'qty': D(str(qty)), 'value': D(str(value)),
        'stock_move_id': extra.pop('move', layer_id),
    }
    event.update(extra)
    return event


def invoice(invoice_id, day, pol, qty, value, month=1, **extra):
    event = {
        'kind': 'invoice', 'seq': (1, invoice_id), 'date': date(2026, month, day), 'group': GROUP_IN,
        'pol': pol, 'invoice_id': invoice_id, 'qty': D(str(qty)), 'value': D(str(value)),
    }
    event.update(extra)
    return event


def adjustments(result, adj_type=None):
    return [(a['type'], a['amount']) for a in result['adjustments']
            if adj_type is None or a['type'] == adj_type]


@tagged('post_install', '-at_install')
class TestKardexEngine(BaseCase):

    def run_engine(self, events, date_from=DF, date_to=DT, **kwargs):
        return KardexEngine(date_from, date_to, **kwargs).run(events)

    def run_all(self, events, date_from=DF, date_to=DT, **kwargs):
        return KardexEngine(date_from, date_to, **kwargs).run_all(events)

    # ------------------------------------------------------------------
    # Promedio y saldo inicial
    # ------------------------------------------------------------------
    def test_opening_uses_odoo_values(self):
        """Antes del período no se recalcula nada: el saldo inicial es la suma
        de los valores de Odoo, aunque el promedio no cuadre."""
        result = self.run_engine([
            ev(1, 1, 10, 1000, month=0),
            ev(2, 5, -5, -700, month=0),
            ev(3, 10, 2, 200),
        ])
        self.assertEqual(result['opening_qty'], D('5'))
        self.assertEqual(result['opening_value'], D('300'))
        self.assertFalse(result['adjustments'])
        self.assertEqual(result['rows'][0]['kind'], ROW_OPENING)

    def test_out_adjusted_to_running_average(self):
        result = self.run_engine([
            ev(1, 2, 10, 1000),
            ev(2, 10, 10, 1300),
            # Odoo valorizó la salida a 100; el promedio vigente es 115
            ev(3, 20, -5, -500),
        ])
        self.assertEqual(adjustments(result), [(ADJ_COST, D('-75.00'))])
        self.assertEqual(result['adjustments'][0]['layer_id'], 3)
        kinds = [r['kind'] for r in result['rows']]
        self.assertEqual(kinds, [ROW_OPENING, ROW_LAYER, ROW_LAYER, ROW_LAYER, ROW_ADJ_COST])
        adj_row = result['rows'][-1]
        # Ajuste negativo: va en la columna Salida, sin signo
        self.assertEqual(adj_row['out_value'], D('75.00'))
        self.assertEqual(adj_row['in_value'], 0)
        self.assertEqual(result['closing_value'], D('1725.00'))
        self.assertEqual(result['raw_closing_value'], D('1800.00'))

    def test_average_chains_previous_adjustments(self):
        result = self.run_engine([
            ev(1, 2, 10, 1000),
            ev(2, 3, -2, -300),   # Odoo 150, promedio 100 -> +100 Entrada
            ev(3, 4, -4, -400),   # promedio (1000-200)/8 = 100 -> 0
        ])
        self.assertEqual([a['amount'] for a in result['adjustments']], [D('100.00')])
        self.assertEqual(result['closing_value'], D('400.00'))

    def test_full_out_leaves_zero_value(self):
        result = self.run_engine([
            ev(1, 2, 3, 100),
            ev(2, 3, -3, -90),
        ])
        self.assertEqual(result['closing_qty'], 0)
        self.assertEqual(result['closing_value'], 0)
        self.assertEqual(result['adjustments'][0]['amount'], D('-10.00'))

    def test_customer_return_origin_cost(self):
        events = [
            ev(1, 2, 10, 1000),
            ev(2, 3, 10, 1300),
            ev(3, 5, -4, -400),  # recalculado 460 (115)
            ev(4, 6, 2, 200, customer_return_origin_id=3),
        ]
        result = self.run_engine(events)
        # Salida: 400 - 460 = -60; devolución: 2 x 115 - 200 = +30
        self.assertEqual([a['amount'] for a in result['adjustments']], [D('-60.00'), D('30.00')])
        result = self.run_engine(events, return_cost_method='current')
        self.assertEqual(result['adjustments'][1]['amount'], D('30.00'))

    def test_customer_return_origin_before_period(self):
        """La salida de origen anterior al período vale lo que tienen sus capas
        (con los ajustes ya registrados)."""
        result = self.run_engine([
            ev(1, 2, 10, 1000, month=0),
            ev(2, 3, -3, -300, month=0),
            ev(3, 4, 0, -60, month=0, move=2),   # ajuste ya registrado de la salida
            ev(4, 3, 3, 330, customer_return_origin_id=2),
        ])
        self.assertEqual(result['adjustments'][0]['amount'], D('30.00'))

    def test_manual_lines_first_in_the_day_and_in_opening(self):
        result = self.run_engine([
            ev(1, 31, 10, 1000, month=0),
            ev(10, 31, 0, -651.11, kind='manual', month=0),
            ev(2, 31, -1, -100),
            ev(11, 31, 0, 651.11, kind='manual'),
        ])
        self.assertEqual(result['opening_value'], D('348.89'))
        kinds = [r['kind'] for r in result['rows']]
        self.assertEqual(kinds[:3], [ROW_OPENING, ROW_MANUAL, ROW_LAYER])
        self.assertFalse(result['adjustments'])

    # ------------------------------------------------------------------
    # R10 y R11: stock negativo y orden dentro del día
    # ------------------------------------------------------------------
    def test_negative_stock_without_history_keeps_odoo_cost(self):
        result = self.run_engine([ev(1, 2, -1, -50)])
        self.assertFalse(result['adjustments'])
        self.assertIn('Sin saldo previo', result['rows'][1]['note'])

    def test_negative_stock_uses_last_positive_average(self):
        """R10: sin saldo, la salida va al último costo promedio positivo, nunca
        a un promedio negativo, y queda marcada para revisión."""
        output = self.run_all([
            ev(1, 2, 10, 1000),
            ev(2, 3, -10, -1000),
            ev(3, 4, -2, -260),
        ])
        result = output['products'][0]
        self.assertEqual(adjustments(result), [(ADJ_COST, D('60.00'))])
        review_rows = [r for r in result['rows'] if r.get('review')]
        self.assertEqual(review_rows[0]['review'], REVIEW_NEGATIVE)
        self.assertEqual(output['warnings'][0]['type'], REVIEW_NEGATIVE)

    def test_inputs_before_outputs_in_the_same_day(self):
        """R11: el mismo día entran primero las compras y luego salen las
        ventas, aunque la venta se haya registrado antes."""
        result = self.run_engine([
            ev(1, 2, 10, 1000),
            ev(2, 5, -15, -1500),          # venta registrada primero
            ev(3, 5, 10, 1300),            # compra registrada después
        ])
        layers = [r for r in result['rows'] if r['kind'] == ROW_LAYER]
        self.assertEqual([r['event']['layer_id'] for r in layers], [1, 3, 2])
        self.assertFalse([r for r in result['rows'] if r.get('review')])
        # Promedio 2300 / 20 = 115 -> 1725
        self.assertEqual(adjustments(result), [(ADJ_COST, D('-225.00'))])

    # ------------------------------------------------------------------
    # R1 y R2: devoluciones a proveedor y reingresos
    # ------------------------------------------------------------------
    def test_vendor_return_at_origin_receipt_cost(self):
        """R1: la devolución sale al costo de su recepción con todas sus capas
        (aquí, una diferencia de precio), no al promedio."""
        result = self.run_engine([
            ev(1, 2, 10, 1000, move=100),
            ev(2, 3, 0, 50, move=100, price_diff=True),
            ev(3, 4, 10, 2000, move=200),
            ev(4, 5, -10, -1525, move=300, role=ROLE_VENDOR_RETURN, origin_move_id=100),
        ])
        self.assertEqual(adjustments(result), [(ADJ_RETURN, D('475.00'))])
        self.assertEqual(result['closing_value'], D('2000.00'))

    def test_reentry_at_return_value_even_if_dated_before(self):
        """R2: el reingreso entra al valor con que sale la devolución que
        revierte (el de la recepción de origen), aunque tenga fecha anterior."""
        result = self.run_engine([
            ev(1, 2, 10, 1000, move=1, pol=7),
            ev(2, 2, 10, 1200, move=3, pol=7, role=ROLE_REENTRY,
               origin_move_id=2, origin_origin_move_id=1),
            ev(3, 6, -10, -900, move=2, pol=7, role=ROLE_VENDOR_RETURN, origin_move_id=1),
        ])
        self.assertEqual(adjustments(result), [(ADJ_RETURN, D('-200.00')), (ADJ_RETURN, D('-100.00'))])
        # Recepción + reingreso - devolución = una recepción
        self.assertEqual(result['closing_qty'], D('10'))
        self.assertEqual(result['closing_value'], D('1000.00'))

    # ------------------------------------------------------------------
    # R3 a R6: factura vs recepción
    # ------------------------------------------------------------------
    def _purchase(self, *extra):
        return [ev(1, 2, 10, 33000, move=1, pol=7)] + list(extra)

    def test_invoice_split_in_exchange_and_price(self):
        """R6: 10 t a USD 1,000 recibidas a TC 3.30 (33,000) y facturadas a
        USD 1,010 a TC 3.35 (33,835): cambio 500 y precio 335."""
        result = self.run_engine(self._purchase(
            invoice(50, 20, 7, 10, 33835, amount_currency=10100, foreign=True, po_price=1000)))
        self.assertEqual(adjustments(result), [(ADJ_FX, D('500.00')), (ADJ_PRICE, D('335.00'))])
        rows = [r for r in result['rows'] if r['kind'] in (ROW_ADJ_FX, ROW_ADJ_PRICE)]
        # R5: fecha de la factura, debajo de la recepción
        self.assertEqual({r['date'] for r in rows}, {date(2026, 1, 20)})
        self.assertEqual({r['event']['layer_id'] for r in rows}, {1})
        self.assertEqual({a['invoice_id'] for a in result['adjustments']}, {50})
        self.assertAlmostEqual(float(rows[0]['tc_invoice']), 3.35)
        self.assertAlmostEqual(float(rows[0]['tc_receipt']), 3.30)
        self.assertEqual(result['closing_value'], D('33835.00'))

    def test_invoice_already_registered_by_odoo(self):
        """R3: si Odoo ya llevó la diferencia (capa de diferencia de precio),
        no se duplica."""
        result = self.run_engine(self._purchase(
            ev(2, 20, 0, 835, move=1, pol=7, price_diff=True),
            invoice(50, 20, 7, 10, 33835, amount_currency=10100, foreign=True, po_price=1000)))
        self.assertFalse(result['adjustments'])

    def test_landed_costs_cover_the_invoice_difference(self):
        """Un costo en destino cuenta como ya registrado hasta cubrir la
        diferencia de la factura."""
        result = self.run_engine(self._purchase(
            ev(2, 3, 0, 800, move=1, pol=7, landed=True),
            invoice(50, 20, 7, 10, 33835)))
        self.assertEqual(adjustments(result), [(ADJ_PRICE, D('35.00'))])

    def test_freight_beyond_the_difference_stays_in_inventory(self):
        """Un flete mayor que la diferencia no se compensa contra la factura
        del proveedor: se queda en el inventario."""
        result = self.run_engine(self._purchase(
            ev(2, 3, 0, 5000, move=1, pol=7, landed=True),
            invoice(50, 20, 7, 10, 33835)))
        self.assertFalse(result['adjustments'])
        self.assertEqual(result['closing_value'], D('38000.00'))

    def test_invoice_and_credit_note(self):
        result = self.run_engine(self._purchase(
            invoice(50, 10, 7, 10, 34000),
            invoice(51, 15, 7, 0, -500)))
        self.assertEqual(adjustments(result), [(ADJ_PRICE, D('1000.00')), (ADJ_PRICE, D('-500.00'))])
        self.assertEqual(result['closing_value'], D('33500.00'))

    def test_more_invoiced_than_received_is_not_adjusted(self):
        output = self.run_all(self._purchase(invoice(50, 20, 7, 20, 67000)))
        self.assertFalse(output['products'][0]['adjustments'])
        self.assertEqual(output['warnings'][0]['type'], REVIEW_PURCHASE)
        self.assertIn('mayor que recibido', output['warnings'][0]['text'])

    def test_partial_invoice(self):
        result = self.run_engine(self._purchase(
            invoice(50, 10, 7, 4, 13400),
            invoice(51, 20, 7, 6, 20100)))
        # 4 t facturadas a 3,350 contra 3,300: +200; luego +300
        self.assertEqual(adjustments(result), [(ADJ_PRICE, D('200.00')), (ADJ_PRICE, D('300.00'))])

    def test_return_and_reentry_get_one_invoice_adjustment(self):
        """R4: recepción devuelta y vuelta a recibir: un solo ajuste por la
        factura, sobre el reingreso (lo que quedó en el almacén)."""
        result = self.run_engine(self._purchase(
            ev(2, 3, -10, -32000, move=2, pol=7, role=ROLE_VENDOR_RETURN, origin_move_id=1),
            ev(3, 4, 10, 33000, move=3, pol=7, role=ROLE_REENTRY, origin_move_id=2,
               origin_origin_move_id=1),
            invoice(50, 20, 7, 10, 33835)))
        invoice_adjustments = [a for a in result['adjustments'] if a['type'] in (ADJ_FX, ADJ_PRICE)]
        self.assertEqual(len(invoice_adjustments), 1)
        self.assertEqual(invoice_adjustments[0]['layer_id'], 3)
        self.assertEqual(invoice_adjustments[0]['amount'], D('835.00'))
        # La devolución salió al costo de la recepción: el ciclo es neutro
        self.assertEqual(adjustments(result, ADJ_RETURN), [(ADJ_RETURN, D('-1000.00'))])
        self.assertEqual(result['closing_value'], D('33835.00'))

    def test_invoice_in_next_month(self):
        """R5: la factura de febrero de una recepción de enero se ajusta en
        febrero, con la fecha de la factura."""
        events = self._purchase(invoice(50, 3, 7, 10, 33835, month=2))
        self.assertFalse(self.run_engine(events)['adjustments'])
        february = self.run_engine(events, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))
        self.assertEqual(adjustments(february), [(ADJ_PRICE, D('835.00'))])
        self.assertEqual(february['adjustments'][0]['date'], date(2026, 2, 3))
        self.assertEqual(february['adjustments'][0]['layer_id'], 1)

    def test_previous_invoice_adjustment_is_registered_value(self):
        """Un ajuste ya registrado de la compra cuenta como registrado."""
        result = self.run_engine(self._purchase(
            ev(2, 3, 0, 835, move=1, pol=7, adj_type=ADJ_FX),
            invoice(50, 20, 7, 10, 33835)))
        self.assertFalse(result['adjustments'])

    # ------------------------------------------------------------------
    # R8 y R9: fabricaciones y desmontajes
    # ------------------------------------------------------------------
    def test_consumption_adjustment_goes_to_finished_product(self):
        """R8: el consumo sale al promedio (500) y su ajuste (+100) baja el
        fabricado de 600 a 500; nada se queda en la cuenta de producción."""
        finished = {20: (2, 20, D('600'), {})}
        output = self.run_all([
            ev(1, 2, 10, 1000, product=1),
            ev(10, 5, -5, -600, product=1, group=GROUP_PRODUCTION, seq=(10, 0, 10),
               role=ROLE_MO_CONSUME, mo_finished=finished),
            ev(20, 5, 1, 600, product=2, group=GROUP_PRODUCTION, seq=(10, 1, 20),
               role=ROLE_MO_PRODUCE, mo_finished=finished),
        ])
        component, product = output['products'][1], output['products'][2]
        self.assertEqual(adjustments(component), [(ADJ_COST, D('100.00'))])
        self.assertEqual(adjustments(product), [(ADJ_PROD, D('-100.00'))])
        self.assertEqual(product['adjustments'][0]['layer_id'], 20)
        self.assertEqual(product['closing_value'], D('500.00'))
        self.assertEqual(product['rows'][-1]['kind'], ROW_ADJ_PROD)

    def test_consumption_after_production_still_transfers(self):
        finished = {20: (2, 20, D('600'), {})}
        output = self.run_all([
            ev(1, 2, 10, 1000, product=1),
            ev(20, 3, 1, 600, product=2, group=GROUP_PRODUCTION, seq=(10, 1, 20),
               role=ROLE_MO_PRODUCE, mo_finished=finished),
            ev(10, 5, -5, -600, product=1, group=GROUP_PRODUCTION, seq=(10, 0, 10),
               role=ROLE_MO_CONSUME, mo_finished=finished),
        ])
        product = output['products'][2]
        self.assertEqual(adjustments(product), [(ADJ_PROD, D('-100.00'))])
        self.assertEqual(product['adjustments'][0]['layer_id'], 20)
        self.assertEqual(product['adjustments'][0]['date'], date(2026, 1, 5))

    def test_unbuild_is_neutral(self):
        """R9: los componentes vuelven a su costo de consumo en la orden y el
        producto sale por esa suma (400), sin importar su promedio."""
        output = self.run_all([
            ev(1, 2, 10, 1000, product=1),            # A a 100
            ev(2, 2, 10, 500, product=3),             # B a 50
            ev(10, 3, -3, -300, product=1),           # consumos de la orden
            ev(11, 3, -2, -100, product=3),
            ev(20, 3, 1, 500, product=2),             # fabricado F
            ev(30, 6, -1, -600, product=2, group=GROUP_PRODUCTION, seq=(30, 0, 30),
               role=ROLE_UB_OUT, ub_components=[
                   {'layers': {31: D('3')}, 'qty': D('3'), 'raw_moves': [10], 'odoo_value': D('300')},
                   {'layers': {32: D('2')}, 'qty': D('2'), 'raw_moves': [11], 'odoo_value': D('200')},
               ]),
            ev(31, 6, 3, 300, product=1, group=GROUP_PRODUCTION, seq=(30, 1, 31), role=ROLE_UB_IN),
            ev(32, 6, 2, 200, product=3, group=GROUP_PRODUCTION, seq=(30, 1, 32), role=ROLE_UB_IN),
        ])
        products = output['products']
        # A vuelve a 3 x 100 = 300 y B a 2 x 50 = 100: F sale por 400 (Odoo 600)
        self.assertEqual(adjustments(products[2]), [(ADJ_PROD, D('200.00'))])
        self.assertFalse(products[1]['adjustments'])
        # B volvió en Odoo a 100 por unidad pero se consumió a 50
        self.assertEqual(adjustments(products[3]), [(ADJ_PROD, D('-100.00'))])
        # Neutro: sale F por 400 y vuelven A por 300 y B por 100
        out_row = [r for r in products[2]['rows'] if r.get('recalc') is not None][0]
        self.assertEqual(out_row['recalc'], D('400.00'))
        back = sum(r['in_value'] for p in (1, 3) for r in products[p]['rows']
                   if r['kind'] != ROW_OPENING and r['date'] == date(2026, 1, 6))
        self.assertEqual(back - D('100.00'), D('400.00'))

    def test_production_chain_keeps_real_order_in_the_day(self):
        """Orden de fabricación, su desmontaje y la orden que la rehace el
        mismo día: cada una en su turno, sin negativos ni ajustes."""
        f1 = {20: (2, 20, D('500'), {})}
        f2 = {50: (2, 50, D('500'), {})}
        output = self.run_all([
            ev(1, 2, 10, 1000, product=1),
            ev(60, 5, -1, -500, product=2),   # venta del fabricado
            ev(10, 5, -5, -500, product=1, group=GROUP_PRODUCTION, seq=(10, 0, 10),
               role=ROLE_MO_CONSUME, mo_finished=f1),
            ev(20, 5, 1, 500, product=2, group=GROUP_PRODUCTION, seq=(10, 1, 20),
               role=ROLE_MO_PRODUCE, mo_finished=f1),
            ev(30, 5, -1, -500, product=2, group=GROUP_PRODUCTION, seq=(30, 0, 30),
               role=ROLE_UB_OUT, ub_components=[
                   {'layers': {31: D('5')}, 'qty': D('5'), 'raw_moves': [10], 'odoo_value': D('500')}]),
            ev(31, 5, 5, 500, product=1, group=GROUP_PRODUCTION, seq=(30, 1, 31), role=ROLE_UB_IN),
            ev(40, 5, -5, -500, product=1, group=GROUP_PRODUCTION, seq=(40, 0, 40),
               role=ROLE_MO_CONSUME, mo_finished=f2),
            ev(50, 5, 1, 500, product=2, group=GROUP_PRODUCTION, seq=(40, 1, 50),
               role=ROLE_MO_PRODUCE, mo_finished=f2),
        ])
        self.assertFalse(output['warnings'])
        product = output['products'][2]
        self.assertEqual([r['event']['layer_id'] for r in product['rows'] if r['kind'] == ROW_LAYER],
                         [20, 30, 50, 60])
        self.assertFalse(product['adjustments'])
        self.assertEqual(product['closing_qty'], 0)

    def test_invoice_before_receipt_adjusts_at_receipt(self):
        """Factura anterior a la recepción: se ajusta cuando llega la recepción,
        con su fecha (no hay inventario en la fecha de la factura)."""
        result = self.run_engine([
            invoice(50, 5, 7, 10, 34000, amount_currency=10000, foreign=True, po_price=1000),
            ev(1, 10, 10, 33000, move=1, pol=7),
        ])
        self.assertEqual(adjustments(result), [(ADJ_FX, D('1000.00'))])
        self.assertEqual(result['adjustments'][0]['date'], date(2026, 1, 10))
        self.assertEqual(result['adjustments'][0]['invoice_id'], 50)

    def test_invoice_before_period_and_receipt_in_period(self):
        result = self.run_engine([
            dict(invoice(50, 28, 7, 10, 34000), date=date(2025, 12, 28)),
            ev(1, 10, 10, 33000, move=1, pol=7),
        ])
        self.assertEqual(adjustments(result), [(ADJ_PRICE, D('1000.00'))])

    def test_odoo_price_difference_posted_later_is_not_duplicated(self):
        """Odoo registra la diferencia de precio de la factura con un asiento de
        fecha posterior: el kardex la cuenta como ya registrada y no ajusta
        ni en el mes de la factura ni cuando llega la capa."""
        events = self._purchase(
            invoice(50, 5, 7, 10, 33835, price_diff_value=835),
            ev(2, 3, 0, 835, month=2, move=1, pol=7, price_diff=True, invoice_id=50),
        )
        self.assertFalse(self.run_engine(events)['adjustments'])
        february = self.run_engine(events, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))
        self.assertFalse(february['adjustments'])
        self.assertEqual(february['closing_value'], D('33835.00'))

    def test_negative_stock_covered_at_next_receipt_cost(self):
        """Las unidades vendidas con stock negativo se regularizan al costo de la
        entrada que las cubre (vacuum de Odoo): el saldo queda al costo de esa
        entrada y el ajuste va debajo de la salida, con la fecha de la entrada."""
        result = self.run_engine([
            ev(1, 2, 10, 1000),
            ev(2, 3, -15, -1500),   # 5 unidades sin saldo, al promedio 100
            ev(3, 6, 10, 1300),     # entrada a 130
        ])
        self.assertEqual(adjustments(result), [(ADJ_COST, D('-150.00'))])
        self.assertEqual(result['adjustments'][0]['layer_id'], 2)
        self.assertEqual(result['adjustments'][0]['date'], date(2026, 1, 6))
        self.assertEqual(result['closing_qty'], D('5'))
        self.assertEqual(result['closing_value'], D('650.00'))

    def test_vendor_return_emptying_stock_takes_remaining_value(self):
        """Si la devolución deja el producto en cero, se lleva todo el saldo:
        nunca queda valor sin cantidad."""
        result = self.run_engine([
            ev(1, 2, 10, 1000, move=100),
            ev(2, 3, 10, 2000, move=200),
            ev(3, 4, -15, -2250),
            ev(4, 5, -5, -500, move=300, role=ROLE_VENDOR_RETURN, origin_move_id=100),
        ])
        self.assertEqual(result['closing_qty'], 0)
        self.assertEqual(result['closing_value'], D('0.00'))

    def test_return_after_partial_invoice_keeps_purchase_balanced(self):
        """La factura cubre solo lo que queda; la devolución posterior sale al
        costo de la recepción y la compra se vuelve a cuadrar con la factura."""
        result = self.run_engine([
            ev(1, 2, 10, 1000, move=1, pol=7),
            invoice(50, 3, 7, 4, 380),
            ev(2, 5, -6, -600, move=2, pol=7, role=ROLE_VENDOR_RETURN, origin_move_id=1),
        ])
        # Al final lo que quedó de la compra (4) vale lo facturado
        self.assertEqual(result['closing_qty'], D('4'))
        self.assertEqual(result['closing_value'], D('380.00'))

    def test_landed_cost_after_invoice_covers_the_adjustment(self):
        """Costo en destino posterior a la factura (P01005): cubre la
        diferencia que el kardex ya había ajustado."""
        result = self.run_engine(self._purchase(
            invoice(50, 10, 7, 10, 33835),
            ev(2, 20, 0, 835, move=1, pol=7, landed=True)))
        self.assertEqual(adjustments(result), [(ADJ_PRICE, D('835.00')), (ADJ_PRICE, D('-835.00'))])
        self.assertEqual(result['closing_value'], D('33835.00'))

    def test_invoice_quantity_rounding_is_tolerated(self):
        """Factura con tres decimales (10.003) contra recepción con dos (10.00):
        no es «facturado mayor que recibido»."""
        output = self.run_all(self._purchase(invoice(50, 20, 7, '10.003', 33835)))
        self.assertFalse(output['warnings'])
        self.assertEqual(adjustments(output['products'][0]), [(ADJ_PRICE, D('835.00'))])

    def test_negative_opening_balance_covered_in_period(self):
        """Saldo inicial negativo (mes anterior): la primera entrada del mes lo
        regulariza a su costo, igual que si se procesara todo de corrido."""
        events = [
            ev(1, 2, 10, 1000),
            ev(2, 20, -15, -1500),        # 5 sin saldo, a 100
            ev(3, 6, 10, 1300, month=2),  # entrada de febrero a 130
        ]
        february = self.run_engine(events, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))
        self.assertEqual(february['opening_qty'], D('-5'))
        self.assertEqual(adjustments(february), [(ADJ_COST, D('-150.00'))])
        self.assertEqual(february['adjustments'][0]['layer_id'], 2)
        self.assertEqual(february['closing_value'], D('650.00'))
