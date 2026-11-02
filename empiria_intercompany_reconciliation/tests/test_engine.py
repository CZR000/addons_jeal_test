from datetime import date

from odoo.tests import TransactionCase, tagged

from ..engine import Engine, document_numbers, normalize_document, pair_key, review_key

A, B, C = 1, 2, 3


@tagged('post_install', '-at_install')
class TestIcEngine(TransactionCase):
    """Reglas del motor con apuntes sintéticos (casos del diseño funcional)."""

    def setUp(self):
        super().setUp()
        self.next_id = 0
        self.rows = []
        self.companies = {
            A: {'name': 'JE-AL', 'legal_name': 'JE-AL ENTERPRISES INC S.A.C.', 'first_date': date(2024, 1, 1)},
            B: {'name': 'Connected', 'legal_name': 'CONNECTED RESOURCES S.A.C.', 'first_date': date(2024, 1, 1)},
            C: {'name': 'EQ', 'legal_name': 'EQUIPAMIENTO LOS ANDES S.A.C.', 'first_date': date(2025, 1, 1)},
        }

    def line(self, company, partner, balance, amount_currency=None, currency='PEN', account='1212001',
             move=None, move_type='entry', doc=None, doc_total=None, day=10, month=9, journal_type='bank',
             journal_code='BNK1', journal_name='Banco', label='', is_fx=False, block=None, reversed_move=None):
        self.next_id += 1
        kind, serie, number = doc if doc else (None, None, None)
        row = {
            'id': self.next_id, 'company': company, 'partner_company': partner,
            # Bloque = la empresa que cobra (por cobrar: la propia; por pagar: el socio).
            'block': block or (company if account[0] == '1' else partner),
            'family': 'loan' if account[:2] in ('16', '17', '46') else 'commercial',
            'account_code': account, 'journal_type': journal_type, 'journal_code': journal_code,
            'journal_name': journal_name, 'is_fx_journal': is_fx, 'move_id': move or 1000 + self.next_id,
            'move_name': f'M{move or 1000 + self.next_id}', 'move_type': move_type, 'doc_kind': kind,
            'doc_serie': serie, 'doc_number': number, 'doc_type_code': '01' if kind else '',
            'doc_total': doc_total if doc_total is not None else abs(amount_currency if amount_currency is not None else balance),
            'move_currency': currency, 'date': date(2026, month, day), 'currency': currency,
            'amount_currency': balance if amount_currency is None else amount_currency, 'balance': balance,
            'label': label, 'ref': '', 'reversed_move_id': reversed_move,
        }
        self.rows.append(row)
        return row

    def invoice(self, issuer, receiver, amount, number='1490', serie='F001', receiver_serie=None, receiver_number=None,
                receiver_amount=None, currency='PEN', rate=1.0, receiver_rate=None, kind='invoice', day=10,
                receiver_day=None, register=True, doc_total=None, receiver_doc_total=None, month=9, receiver_month=None):
        sign = 1 if kind != 'refund' else -1
        sale = self.line(issuer, receiver, sign * round(amount * rate, 2), sign * amount, currency, '1212001',
                         move_type='out_invoice' if kind != 'refund' else 'out_refund', doc=(kind, serie, number),
                         doc_total=doc_total if doc_total is not None else amount, day=day, month=month,
                         journal_type='sale', journal_code='01')
        if not register:
            return sale, None
        receiver_amount = amount if receiver_amount is None else receiver_amount
        purchase = self.line(receiver, issuer, -sign * round(receiver_amount * (receiver_rate or rate), 2),
                             -sign * receiver_amount, currency, '4212001',
                             move_type='in_invoice' if kind != 'refund' else 'in_refund',
                             doc=(kind, receiver_serie or serie, receiver_number or number),
                             doc_total=receiver_doc_total if receiver_doc_total is not None else receiver_amount,
                             day=receiver_day or day, month=receiver_month or month, journal_type='purchase',
                             journal_code='FACTU')
        return sale, purchase

    def reconcile(self, **kwargs):
        engine = Engine(self.companies, self.rows, **kwargs)
        pairs, details = engine.run()
        self.assertTrue(all(abs(pair['control']) < 0.005 for pair in pairs.values()), 'control = 0 en todos los pares')
        self.engine = engine
        return pairs, details

    def groups(self, rule):
        return [group for group in self.engine.groups if group.rule == rule]

    @staticmethod
    def key(creditor, debtor):
        """Par y bloque: la empresa que cobra y la que paga."""
        return pair_key(creditor, debtor, creditor)

    def categories(self, details):
        return sorted(detail['category'] for detail in details)

    # Comprobantes ------------------------------------------------------- #

    def test_invoice_matched_by_number(self):
        self.invoice(A, B, 1180.0, number='1490')
        pairs, details = self.reconcile()
        self.assertEqual(details, [], 'Conciliado sin efecto: no deja detalle')
        self.assertEqual(pairs[self.key(A, B)]['difference'], 0.0)
        self.assertEqual(pairs[self.key(A, B)]['matched_count'], 1)

    def test_invoice_not_registered_with_draft_note(self):
        """Caso 2: EQ → JE-AL F001-1491 en borrador en JE-AL."""
        self.invoice(C, A, 2033.52, number='1491', currency='USD', rate=3.36, register=False, doc_total=0.0)
        lookup = lambda company, kind, serie, number: [{'move_name': 'F RC/2026/09/0091', 'state': 'draft', 'partner_company': C}]
        pairs, details = self.reconcile(receiver_lookup=lookup)
        self.assertEqual(self.categories(details), ['unregistered_receiver'])
        self.assertIn('registrada en borrador en JE-AL (F RC/2026/09/0091)', details[0]['note'])
        self.assertIn('factura final con aplicación de anticipos (total 0)', details[0]['note'])
        self.assertAlmostEqual(details[0]['effect_pen'], pairs[self.key(C, A)]['difference'])

    def test_purchase_without_issuer(self):
        self.line(B, A, -500.0, move_type='in_invoice', doc=('invoice', 'F001', '77'), journal_type='purchase')
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['no_issuer'])

    def test_credit_note_with_other_serie(self):
        """Caso 3: NC C01-81 en el emisor, FC01-81 en el receptor, efecto 0.02."""
        self.invoice(A, C, 140926.98, serie='C01', number='81', receiver_serie='FC01', kind='refund',
                     currency='USD', rate=3.75, receiver_rate=3.7499999)
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['serie_diff'])
        self.assertIn('FC01-81', details[0]['note'])

    def test_document_with_other_number(self):
        self.invoice(A, B, 300.0, number='10', receiver_number='11', receiver_day=12)
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['number_diff'])

    def test_advance_applied_differently(self):
        """Caso 4: total USD 100,000 en ambas, en cuentas IC 100,000 vs 15,254.24."""
        sale, purchase = self.invoice(C, A, 100000.0, serie='E001', number='247', currency='USD', rate=3.722,
                                      receiver_amount=15254.24, receiver_doc_total=100000.0, month=9)
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['advance_diff'])
        self.assertIn('100,000.00 vs 15,254.24', details[0]['note'])

    def test_rounding_and_rate_difference(self):
        """Caso 5: mismo TC, efecto 0.01 → redondeo; otro TC → tipo de cambio distinto."""
        self.invoice(A, B, 605292.48, number='1729', currency='USD', rate=3.45)
        self.rows[-1]['balance'] -= 0.01
        self.invoice(A, B, 1000.0, number='1730', currency='USD', rate=3.45, receiver_rate=3.40)
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['rate_diff', 'rounding'])

    def test_period_and_currency_difference(self):
        self.invoice(A, B, 500.0, number='20', currency='USD', rate=3.4, receiver_rate=3.5, month=8, receiver_month=9)
        sale, purchase = self.invoice(A, B, 100.0, number='21')
        purchase['move_currency'] = 'USD'
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['currency_diff', 'period_diff'])

    # Movimientos -------------------------------------------------------- #

    def test_payment_line_against_line(self):
        """Un asiento de la otra empresa con varias líneas (detracciones juntas)."""
        self.line(A, B, -37286.0, journal_code='BND', journal_name='Banco de Detracciones', day=9)
        self.line(A, B, -24099.0, journal_code='BND', journal_name='Banco de Detracciones', day=9)
        self.line(B, A, 37286.0, move=500, day=8, account='4212001')
        self.line(B, A, 24099.0, move=500, day=8, account='4212001')
        self.line(B, A, 428.0, move=500, day=8, account='4212001')
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['payment'], 'Solo queda la línea de 428 sin contrapartida')
        self.assertEqual(details[0]['amount_pen'], 428.0)

    def test_payment_in_other_currency_and_grouped(self):
        self.line(A, B, -3450.0, -1000.0, 'USD', day=1)
        self.line(B, A, 3449.0, day=3, account='4212001')       # regla 11: en soles
        self.line(A, B, -100.0, day=5)
        self.line(A, B, -50.0, day=5)
        self.line(B, A, 150.0, day=15, account='4212001')       # regla 12: suma del día
        pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['currency_diff'], 'USD en una empresa y PEN en la otra')
        self.assertEqual(details[0]['pending'], False, 'Moneda distinta en un pago: conciliado con observación')
        self.assertIn('USD en JE-AL, PEN en Connected; diferencia S/ -1.00', details[0]['note'])
        self.assertEqual(pairs[self.key(A, B)]['by_category']['currency_diff'], -1.0)
        self.assertEqual(pairs[self.key(A, B)]['pending_count'], 0)

    def test_detraction_retention_opening_and_manual(self):
        """Casos 6, 7 y 9: sin contrapartida según el diario."""
        self.line(A, B, -24386.0, journal_code='BNK3', journal_name='Banco de Detracciones')
        self.line(A, B, 15283.31, journal_type='general', journal_code='001', journal_name='Comprobante de retención')
        self.line(A, B, 322353.33, journal_type='general', journal_code='APERT', journal_name='APERTURA')
        self.line(A, B, 1000.0, journal_type='general', journal_code='Vario', journal_name='Provisiones varias')
        self.line(A, B, 2.7, journal_type='general', journal_code='Vario', journal_name='Provisiones varias',
                  label='AJUSTE POR REDONDEO AL PAGO')
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['detraction', 'manual_entry', 'manual_entry', 'opening', 'retention'],
                         'N7: un asiento manual sin contrapartida es siempre asiento manual, aunque diga redondeo')
        rounding = next(d for d in details if d['amount_pen'] == 2.7)
        self.assertIn('ajuste por redondeo sin contrapartida', rounding['note'])
        self.assertTrue(rounding['pending'])

    def test_no_effect_entries(self):
        self.line(A, B, 500.0, move=900, journal_type='general', journal_code='Vario', journal_name='Prov')
        self.line(A, B, -500.0, move=900, account='1699001', journal_type='general', journal_code='Vario', journal_name='Prov')
        self.line(A, B, 1800.0, 6291.0 / 3.495, 'USD', journal_type='general', journal_code='Vario', journal_name='Prov', month=3)
        self.rows[-1]['amount_currency'] = 1800.0
        self.rows[-1]['balance'] = 6291.0
        self.line(A, B, -6184.8, -1800.0, 'USD', journal_type='general', journal_code='Vario', journal_name='Prov', month=4)
        pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['fx', 'no_effect'], 'Provisión y extorno: el residuo es dif. de cambio')

    def test_triangular_compensation(self):
        """Caso 8: Connected paga a EQ por cuenta de Central (aquí A paga a C por cuenta de B)."""
        self.line(A, B, 150000.0, 150000.0, 'USD', account='1699001', label='PAGO REALIZADO A EQUIPAMIENTO - COMPENSACION')
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['triangular_incomplete'])
        self.assertIn('falta registrar en EQ, Connected', details[0]['note'])

        self.line(C, A, -150000.0, -150000.0, 'USD', account='1212001', journal_type='bank', day=11)
        self.line(B, C, 150000.0, 150000.0, 'USD', account='4212001', journal_type='general', journal_code='Vario',
                  journal_name='Prov', day=12)
        _pairs, details = self.reconcile()
        self.assertEqual(set(self.categories(details)), {'triangular'})

    def test_other_account_family_is_matched_with_note(self):
        """N1/N2: préstamo con JE-AL en 46 y Connected en 12: mismo bloque (Connected cobra),
        conciliado con la observación de cuenta distinta."""
        self.line(A, B, -101000.0, account='4699001', label='PRESTAMO JEAL - CONNECTED')
        self.line(B, A, 101000.0, account='1212001', day=11)
        pairs, details = self.reconcile()
        self.assertEqual(list(pairs), [self.key(B, A)], 'Un solo bloque: Connected por cobrar / JE-AL por pagar')
        self.assertEqual(self.categories(details), ['matched_account'])
        self.assertEqual(details[0]['account_note'], 'JE-AL en 4699001 / Connected en 1212001')
        self.assertFalse(details[0]['pending'])
        self.assertEqual(pairs[self.key(B, A)]['pending_count'], 0)

    def test_outcall_invoices_in_46(self):
        """N2: facturas de EQ que el receptor registró en 4699001: conciliadas por número, con la observación."""
        for number, amount in (('828', 12934.23), ('829', 697.21), ('975', 417.43)):
            sale, purchase = self.invoice(C, B, amount, number=number)
            purchase['account_code'] = '4699001'
            purchase['family'] = 'loan'
        pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['matched_account'] * 3)
        self.assertEqual({d['account_note'] for d in details}, {'Connected en 4699001 / EQ en 1212001'})
        self.assertEqual({d['note'] for d in details},
                         {'Documento en ambas empresas, en cuentas distintas (Connected en 4699001 / EQ en 1212001)'},
                         'P4: la observación se ve en la columna Observación')
        self.assertEqual(pairs[self.key(C, B)]['difference'], 0.0)

    def test_two_blocks_per_pair(self):
        """N1: A cobra a B y B cobra a A son bloques distintos; cada uno cuadra por sí mismo."""
        self.invoice(A, B, 100.0, number='1')
        self.invoice(B, A, 70.0, number='2', register=False)
        pairs, _details = self.reconcile()
        self.assertEqual(pairs[self.key(A, B)]['difference'], 0.0)
        self.assertEqual(pairs[self.key(B, A)]['difference'], 70.0)

    def test_fx_journal(self):
        for _i in range(3):
            self.line(A, B, 0.39, 0.0, 'USD', journal_type='general', journal_code='CAMBI', is_fx=True)
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['fx'])
        self.assertEqual(details[0]['line_count'], 3)

    def test_manual_match_has_priority(self):
        """Caso 12: lo emparejado a mano sale como Conciliado manual con la diferencia aceptada."""
        a = self.line(A, B, -387363.89, -103656.38, 'USD', day=16, month=8)
        b = self.line(B, A, 378713.15, 101341.49, 'USD', day=16, month=8, account='4212001')
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['payment', 'payment'])
        pairs, details = self.reconcile(manual_matches=[{'id': 7, 'line_ids': {a['id'], b['id']}, 'reason': 'Otro: comisión'}])
        self.assertEqual(self.categories(details), ['manual_match'])
        self.assertAlmostEqual(details[0]['effect_pen'], -8650.74)

    def test_document_number_normalization(self):
        self.assertEqual(normalize_document('F 001-00001490'), ('F001', '1490'))
        self.assertEqual(normalize_document(' fc01-81 '), ('FC01', '81'))
        self.assertEqual(normalize_document('F RC/2026/09/0091'), (None, None))

    def test_review_key_changes_with_amount(self):
        self.assertNotEqual(review_key(A, [10], 100.0), review_key(A, [10], 100.01))
        self.assertEqual(review_key(A, [10], 100.004), review_key(A, [10], 100.0))
        self.assertNotEqual(review_key(A, [10], 100.0), review_key(A, [11], 100.0))
        self.assertLess(len(review_key(A, list(range(5000)), 1.0)), 64, 'Huella de longitud fija')

    def test_before_counterpart_start_note(self):
        self.invoice(A, C, 100.0, number='5', register=False, month=9)
        self.rows[-1]['date'] = date(2024, 6, 1)
        _pairs, details = self.reconcile()
        self.assertIn('anterior al inicio en Odoo de EQ (01/01/2025)', details[0]['note'])

    # Periodo (desde - hasta) -------------------------------------------- #

    def test_period_summarizes_previous_differences(self):
        """Con fecha desde, lo anterior se resume en una línea por par y el control sigue en 0."""
        self.invoice(A, B, 300.0, number='10', register=False, month=7)    # anterior, sin registrar
        self.invoice(A, B, 200.0, number='11', register=False, month=8)    # anterior, sin registrar
        self.invoice(A, B, 1000.0, number='12', month=8)                   # anterior, conciliada
        self.invoice(A, B, 50.0, number='13', register=False, month=9)     # del periodo
        self.invoice(A, B, 80.0, number='14', month=8, receiver_month=9)   # cruza el inicio del periodo
        pairs, details = self.reconcile(date_from=date(2026, 9, 1))
        pair = pairs[self.key(A, B)]
        self.assertEqual(self.categories(details), ['matched', 'prior_period', 'unregistered_receiver'])
        prior = next(d for d in details if d['category'] == 'prior_period')
        self.assertEqual(prior['effect_pen'], 580.0, 'P3: todo lo anterior a la fecha desde va al arrastre')
        self.assertEqual(prior['date'], date(2026, 8, 31))
        self.assertIn('2 partidas pendientes', prior['note'])
        self.assertEqual(pair['by_category']['prior_period'], pair['opening_difference'])
        self.assertEqual(pair['by_category']['unregistered_receiver'], 50.0)
        crossing = next(d for d in details if d['category'] == 'matched')
        self.assertEqual(crossing['effect_pen'], -80.0, 'En el periodo solo la compra registrada en septiembre')
        self.assertIn('S/ 80.00 de apuntes anteriores al 01/09/2026 van en el arrastre', crossing['note'])
        self.assertEqual(pair['difference'], 550.0, 'El saldo es el acumulado al corte')
        self.assertEqual(pair['opening_difference'], 580.0, 'Al 31/08 faltaba registrar 10, 11 y 14')
        self.assertEqual(pair['pending_count'], 1, 'Solo cuenta lo del periodo')

    def test_period_without_date_from_is_cumulative(self):
        self.invoice(A, B, 300.0, number='10', register=False, month=7)
        self.invoice(A, B, 50.0, number='13', register=False, month=9)
        pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['unregistered_receiver', 'unregistered_receiver'])
        self.assertEqual(pairs[self.key(A, B)]['opening_difference'], 0.0)

    # Ajustes de la nota del 09/10/2026 ---------------------------------- #

    def test_same_amount_in_usd_is_rate_or_rounding(self):
        """N5: mismo importe en USD en ambas, distinto en soles: tipo de cambio (o redondeo ≤ 1)."""
        self.invoice(A, B, 15841.05, number='1573', currency='USD', rate=3.7)
        self.rows[-1]['balance'] += 31.67
        self.invoice(A, B, 2000.0, number='70', currency='USD', rate=3.7)
        self.rows[-1]['balance'] += 0.95
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['rate_diff', 'rounding'])
        self.assertFalse(next(d for d in details if d['category'] == 'rounding')['pending'], 'N7: redondeo ≤ 1 conciliado')
        self.assertIn('Diferencia de redondeo S/ 0.95', next(d for d in details if d['category'] == 'rounding')['note'])

    def test_document_currency_differs(self):
        """N4: la factura en USD en el emisor y en PEN en el receptor es Moneda distinta aunque el efecto sea 0."""
        sale, purchase = self.invoice(A, B, 2000.01, number='55', currency='USD', rate=3.38)
        purchase.update({'move_currency': 'PEN', 'currency': 'PEN', 'amount_currency': purchase['balance'] + 0.03,
                         'balance': purchase['balance'] + 0.03, 'doc_total': 6760.0})
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['currency_diff'])
        self.assertFalse(details[0]['pending'], 'Efecto mínimo: conciliado con la observación')
        self.assertIn('USD en JE-AL, PEN en Connected', details[0]['note'])

    def test_serie_with_counterpart_zero(self):
        """N6: C01-101 contra FC01-101 con importe 0 en las cuentas IC: sin registrar en el receptor."""
        sale, purchase = self.invoice(A, C, 14142.73, serie='C01', number='101', receiver_serie='FC01', kind='refund')
        purchase.update({'balance': 0.0, 'amount_currency': 0.0})
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['unregistered_receiver'])
        self.assertIn('con importe 0 en las cuentas intercompany', details[0]['note'])

    def test_rounding_limit(self):
        """N7: total distinto por 0.50 USD pero efecto en soles mayor a 1: importe distinto, no redondeo."""
        self.invoice(A, B, 1000.0, number='60', currency='USD', rate=3.7, receiver_amount=999.5)
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['amount_diff'])

    def test_purchase_without_number_note(self):
        """N8: compra sin número en la Referencia: sin factura del emisor con la observación."""
        self.line(B, A, -1550059.81, account='4220001', move_type='in_invoice', doc=('invoice', None, None),
                  journal_type='purchase')
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['no_issuer'])
        self.assertIn('comprobante sin número', details[0]['note'])

    def test_cross_offset_in_one_company_shows_in_both_blocks(self):
        """N1: cruce de cuentas (12 contra 42) solo en una empresa: cada bloque queda con su diferencia."""
        self.line(A, B, -500.0, move=901, journal_type='general', journal_code='Vario', journal_name='Cruce')
        self.line(A, B, 500.0, move=901, account='4212001', journal_type='general', journal_code='Vario', journal_name='Cruce')
        pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['manual_entry', 'manual_entry'])
        self.assertEqual(pairs[self.key(A, B)]['difference'], -500.0)
        self.assertEqual(pairs[self.key(B, A)]['difference'], 500.0)

    def test_same_side_in_both_companies(self):
        """Las dos empresas usan la 122 (ambas por cobrar): bloques opuestos, conciliado con observación."""
        self.line(B, C, -78122.0, account='1220001', day=8)
        self.line(C, B, 78122.0, account='1220001', day=8)
        pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['matched_account', 'matched_account'])
        self.assertEqual({d['account_note'] for d in details}, {'Connected en 1220001 / EQ en 1220001 (las dos por cobrar)'})
        self.assertEqual({d['note'] for d in details}, {
            'Documento en ambas empresas, en cuentas distintas (Connected en 1220001 / EQ en 1220001); las dos por cobrar'})
        self.assertFalse(any(d['pending'] for d in details))
        self.assertEqual(pairs[self.key(B, C)]['difference'] + pairs[self.key(C, B)]['difference'], 0.0)
        self.assertEqual(pairs[self.key(B, C)]['pending_count'], 0)
        self.assertEqual(sorted(d['counterpart_amount_pen'] for d in details), [-78122.0, 78122.0],
                         'Cada línea muestra el documento de la otra empresa (en el otro bloque)')
        self.assertEqual(sorted(d['effect_pen'] for d in details), [-78122.0, 78122.0])

    # Pendientes de la nota del 12/10/2026 ------------------------------ #

    def test_carry_over_equals_opening_difference(self):
        """P3: asientos de diferencia de cambio antes y después de la fecha desde: los
        anteriores van al arrastre, que es igual a la diferencia al inicio."""
        self.line(A, B, 13766.20, 0.0, 'USD', journal_type='general', journal_code='CAMBI', is_fx=True, month=7)
        self.line(A, B, -9049.32, 0.0, 'USD', journal_type='general', journal_code='CAMBI', is_fx=True, month=7, day=20)
        self.line(A, B, 120.0, 0.0, 'USD', journal_type='general', journal_code='CAMBI', is_fx=True, month=9, day=15)
        pairs, details = self.reconcile(date_from=date(2026, 9, 1))
        pair = pairs[self.key(A, B)]
        self.assertAlmostEqual(pair['opening_difference'], 4716.88)
        self.assertAlmostEqual(pair['by_category']['prior_period'], 4716.88)
        self.assertAlmostEqual(pair['by_category']['fx'], 120.0, msg='En el periodo solo el asiento de septiembre')
        self.assertAlmostEqual(pair['opening_difference'] + pair['by_category']['fx'], pair['difference'])

    def test_rate_difference_tolerance(self):
        """P6: centavos de tipo de cambio sobre importes grandes quedan como redondeo."""
        self.invoice(A, B, 13285.0, number='70', currency='USD', rate=3.4216)       # S/ 45,456
        self.rows[-1]['balance'] -= 4.95
        self.invoice(A, B, 72276.0, number='329', currency='USD', rate=3.4216)      # S/ 247,296
        self.rows[-1]['balance'] -= 6.95
        self.invoice(A, B, 2000.0, number='1087', currency='USD', rate=3.478, receiver_rate=3.51)
        _pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['rate_diff', 'rounding', 'rounding'])
        rounding = [d for d in details if d['category'] == 'rounding']
        self.assertFalse(any(d['pending'] for d in rounding))
        self.assertIn('dentro de la tolerancia de tipo de cambio', rounding[0]['note'])
        _pairs, details = self.reconcile(params={'rate_diff_percent': 0.0, 'rate_diff_minimum': 1.0})
        self.assertEqual(self.categories(details), ['rate_diff'] * 3, 'Sin tolerancia: pendientes')

    def test_payment_plus_retention(self):
        """P9.1: el cobro de EQ es igual al pago de JE-AL más la retención del 3%."""
        self.line(C, A, -185567.01, day=16, month=6)
        self.line(A, C, 180000.0, account='4212000', day=16, month=6)
        self.line(A, C, 5567.01, account='4212000', journal_type='general', journal_code='001',
                  journal_name='Comprobante de retención', day=25, month=6)
        pairs, details = self.reconcile()
        self.assertEqual(details, [])
        self.assertEqual(pairs[self.key(C, A)]['pending_count'], 0)
        [group] = self.groups(16)
        self.assertEqual((group.category, group.note, len(group.lines)), ('matched', 'Pago más retención 3%', 3))

    def test_one_payment_against_several(self):
        """P9.2: un pago en USD de JE-AL es la suma de dos cobros y una factura de EQ (en soles)."""
        self.line(A, C, 44382.0, 13000.0, 'USD', account='4212001', day=21, month=5)
        self.line(C, A, -30927.84, day=16, month=5)
        self.line(C, A, -10309.28, day=6, month=5, journal_type='general', journal_code='Vario', journal_name='Varios')
        self.invoice(C, A, -3145.20, number='61', serie='C01', register=False, month=5, day=10)
        pairs, details = self.reconcile()
        self.assertEqual(self.categories(details), ['matched'])
        self.assertEqual(details[0]['note'], 'Pago agrupado: 4 líneas; diferencia S/ -0.32')
        self.assertFalse(details[0]['pending'])
        self.assertEqual(pairs[self.key(C, A)]['pending_count'], 0)
        self.assertEqual(self.groups(17)[0].category, 'matched')

    def test_advance_in_several_parts(self):
        """P9.5: anticipo en tres partes en JE-AL y en un solo asiento en EQ."""
        for day, amount in ((1, -100.0), (15, -200.0), (28, -300.0)):
            self.line(A, C, amount, account='1220001', journal_type='general', journal_code='Vario',
                      journal_name='Varios', label='ANTICIPO POR LA VENTA DE EQUIPOS', day=day, month=3)
        received = self.line(C, A, 600.0, account='4220001', journal_type='general', journal_code='Vario',
                             journal_name='Varios', label='ANTICIPO JEAL', day=10, month=5)
        _pairs, details = self.reconcile()
        self.assertEqual(details, [])
        self.assertEqual(self.groups(18)[0].note, 'Anticipo agrupado: 3 en JE-AL contra 1 en EQ')

        received.update({'balance': 550.0, 'amount_currency': 550.0})
        pairs, details = self.reconcile()
        self.assertEqual(len(details), 4)
        self.assertTrue(all(d['pending'] and d['partial_advance'] for d in details), 'No cuadran: marca para revisar')
        self.assertIn('Anticipo aplicado parcialmente (3 en JE-AL contra 1 en EQ', details[0]['note'])

    def test_suggestions(self):
        """P9.3 y P9.4: posible contraparte por monto parecido o por el comprobante citado en la glosa."""
        refund = self.line(A, B, 1240.08, 363.02, 'USD', label='Devolución a favor de Connected', day=29, month=5)
        self.line(B, A, -1262.95, -363.02, 'USD', account='4699000', journal_type='general', journal_code='Vario',
                  journal_name='Provisiones varias', label='OTRAS CUENTAS POR PAGAR POR ANTICIPO ASUMIDO', day=1, month=5)
        self.line(A, C, 500.0, account='4212000', label='PAGO E 001-00000120', day=1, month=7)
        self.invoice(C, A, 999.0, serie='E001', number='120', register=False, month=7)
        _pairs, details = self.reconcile()
        by_move = {d['move_name']: d for d in details}
        first = by_move[refund['move_name']]
        self.assertIn('el monto difiere 1.8% y la fecha 28 días', first['suggestion_note'])
        self.assertEqual(first['suggestion_ref'], next(d['group_ref'] for d in details if d['company'] == B))
        cited = next(d for d in details if d['company'] == A and d['amount_pen'] == 500.0)
        self.assertIn('la glosa menciona E001-120', cited['suggestion_note'])
        self.assertTrue(all(d['pending'] for d in details), 'Las sugerencias no emparejan')
        self.assertEqual(document_numbers('ANTICIPO: FACTURA NRO. E001-120 y F 001-00001681'), ['E001-120', 'F001-1681'])
