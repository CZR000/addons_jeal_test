"""Motor de la conciliación intercompany por documento.

Python puro (sin Odoo): recibe los apuntes del universo como diccionarios y
devuelve, por par de empresas y bloque de cuentas, los saldos y los grupos que
explican la diferencia. Lo usan el modelo ``ic.reconciliation.run`` y los
scripts de validación contra producción.

Cada apunte termina en exactamente un grupo; el efecto de un grupo en un par es
la suma de los saldos (en soles) de sus apuntes en ese par. Así, para cada par,
diferencia = suma de los efectos de sus grupos y el control es 0 por
construcción (se verifica igual al final).

Bloques: cada par A↔B tiene dos, según quién cobra. El bloque de un apunte es
la empresa acreedora: la propia si la cuenta es por cobrar (12, 13, 14, 16, 17,
19) y el socio si es por pagar (41 a 47). Así una 12 contra una 46 o una 16
contra una 42 caen en el mismo bloque y se emparejan sin tratamiento especial.

Apunte de entrada (``line``):
    id, company, partner_company, block (id de la empresa que cobra),
    family ('commercial' | 'loan', solo para la observación de cuenta distinta), account_code,
    journal_type, journal_code, journal_name, is_fx_journal, move_id, move_name,
    move_type, doc_kind ('invoice' | 'refund' | 'debit' | None), doc_serie,
    doc_number, doc_total (total del comprobante en su moneda), move_currency,
    date (datetime.date), currency, amount_currency, balance, label, ref,
    reversed_move_id
"""
import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import timedelta
from itertools import combinations

BLOCK_LABELS = {'a_receivable': 'A por cobrar / B por pagar', 'b_receivable': 'B por cobrar / A por pagar'}

CATEGORIES = [
    ('unregistered_receiver', 'Factura/NC sin registrar en el receptor',
     'Registrar la compra o NC en la empresa receptora con el mismo número, importe y moneda, o anularla en el emisor.'),
    ('no_issuer', 'Compra sin factura/NC del emisor',
     'Confirmar con el emisor; si no existe, revisar el socio o anular la compra.'),
    ('advance_diff', 'Anticipo/retención aplicado distinto',
     'Igualar los anticipos o retenciones aplicados en la factura final de ambas empresas.'),
    ('amount_diff', 'Importe distinto entre emisor y receptor',
     'Corregir el importe del comprobante en la empresa que lo registró distinto.'),
    ('currency_diff', 'Moneda distinta',
     'Registrar el comprobante en la misma moneda en ambas empresas.'),
    ('rate_diff', 'Tipo de cambio distinto al de la venta',
     'Registrar la compra con el tipo de cambio de la factura de venta.'),
    ('period_diff', 'Documento en periodo distinto',
     'Alinear la fecha contable del comprobante en ambas empresas.'),
    ('rounding', 'Redondeo (≤ 1)',
     'Ajustar por redondeo.'),
    ('serie_diff', 'NC con serie distinta',
     'Corregir la serie en la compra (C01 → FC01); no afecta el saldo.'),
    ('number_diff', 'Documento con número distinto',
     'Corregir el número del comprobante en la empresa que lo registró distinto.'),
    ('payment', 'Pago/cobro sin contrapartida',
     'Registrar el pago o cobro en la otra empresa, o revisar si fue una compensación con una tercera empresa.'),
    ('detraction', 'Detracción sin contrapartida',
     'Registrar el depósito de la detracción en la otra empresa.'),
    ('retention', 'Retención sin contrapartida',
     'Registrar el comprobante de retención en la otra empresa.'),
    ('manual_entry', 'Asiento manual sin contrapartida',
     'Revisar la provisión, préstamo o reclasificación y registrar la contrapartida o revertirla.'),
    ('opening', 'Saldo de apertura sin contrapartida',
     'Comparar las aperturas y ajustar la que no corresponda.'),
    ('triangular', 'Compensación de 3 empresas',
     'Conciliado entre tres empresas: el importe se compensa en los otros pares de la operación.'),
    ('triangular_incomplete', 'Compensación incompleta',
     'Registrar la parte que falta de la compensación en la empresa indicada.'),
    ('manual_match', 'Conciliado manual (diferencia aceptada)',
     'Emparejado a mano; la diferencia se aceptó con el motivo indicado.'),
    ('fx', 'Diferencia de cambio',
     'Uniformizar la política de tipo de cambio entre empresas (compra o venta, fecha).'),
    ('no_effect', 'Anulado en la misma empresa (sin efecto)',
     'Ninguna: el asiento se anula dentro de la misma empresa.'),
    ('prior_period', 'Arrastre anterior al periodo',
     'Partidas anteriores a la fecha desde que siguen pendientes: genere desde una fecha anterior para ver cada una.'),
    ('matched_account', 'Conciliado – cuenta distinta',
     'Ninguna para el saldo: el documento está en ambas empresas por el mismo importe; solo difiere la cuenta '
     '(p.ej. 12 contra 46). Uniformizar la cuenta si corresponde.'),
    ('matched', 'Conciliado', ''),
]
CATEGORY_LABELS = {key: label for key, label, _hint in CATEGORIES}
CATEGORY_HINTS = {key: hint for key, _label, hint in CATEGORIES}
# Categorías que son diferencia real (las demás quedan conciliadas o explicadas).
PENDING_CATEGORIES = {key for key, _l, _h in CATEGORIES} - {
    'matched', 'matched_account', 'triangular', 'no_effect', 'manual_match', 'fx', 'prior_period', 'rounding'}

DEFAULT_PARAMS = {
    'amount_tolerance': 0.05,
    'rounding_tolerance': 1.00,
    'document_total_tolerance': 0.01,
    'number_days': 5,
    'payment_days': 15,
    'grouped_days': 20,
    'triangular_days': 20,
    'other_currency_percent': 1.0,
    'other_currency_minimum': 1.00,
    'rate_diff_percent': 0.02,
    'rate_diff_minimum': 1.00,
    'combination_tolerance': 1.00,
    'suggestion_percent': 2.0,
    'suggestion_days': 30,
}

# Familia préstamos: solo para la observación "cuenta distinta" (p.ej. 12 contra 46).
LOAN_PREFIXES = ('16', '17', '46')
# Retención del IGV (régimen de retenciones).
RETENTION_RATE = 0.03

DOC_RE = re.compile(r'^([A-Z0-9]+)-0*(\d+)$')
# Comprobante citado en una glosa: "E001-120", "F 001-00001681", "FC01-12".
DOC_IN_TEXT_RE = re.compile(r'\b([A-Z]{1,2})\s?(\d{2,3})\s*-\s*0*(\d{1,8})\b')
ADVANCE_RE = re.compile(r'ANTICIP|ADELANT|PRESTAM|DESEMBOLS')
# Reglas 16-18: categorías pendientes que pueden explicarse entre sí.
COMBINABLE_CATEGORIES = {'payment', 'manual_entry', 'unregistered_receiver', 'no_issuer', 'detraction', 'retention'}
MAX_CANDIDATES = 40


def normalize_document(number):
    """'F 001-00001490' / 'f001-1490 ' -> ('F001', '1490')."""
    value = re.sub(r'\s+', '', (number or '').upper())
    match = DOC_RE.match(value)
    if not match:
        return None, None
    return match.group(1), match.group(2) or '0'


def strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text or '') if unicodedata.category(c) != 'Mn')


def document_key(serie, number):
    return f"{serie}-{number}" if serie and number else None


def document_numbers(text):
    """Comprobantes citados en un texto, normalizados: ['E001-120', ...]."""
    return [f"{letters}{digits}-{number}" for letters, digits, number in DOC_IN_TEXT_RE.findall((text or '').upper())]


def pair_key(company_a, company_b, block):
    return (min(company_a, company_b), max(company_a, company_b), block)


def block_code(key):
    """'a_receivable' si cobra la empresa A del par (la de id menor), si no 'b_receivable'."""
    return 'a_receivable' if key[2] == key[0] else 'b_receivable'


class Group:
    """Conjunto de apuntes que la misma regla clasifica juntos."""
    __slots__ = ('category', 'rule', 'lines', 'note', 'counterpart_lines', 'pairs', 'main_company', 'extra')

    def is_pending(self):
        """Diferencia real (pendiente) o explicada. Una regla puede decidirlo en
        ``extra['pending']`` (p.ej. moneda distinta con efecto 0)."""
        return self.extra.get('pending', self.category in PENDING_CATEGORIES)

    def __init__(self, category, rule, lines, note='', extra=None):
        self.category = category
        self.rule = rule
        self.lines = list(lines)
        self.note = note
        self.extra = extra or {}


class Engine:

    def __init__(self, companies, lines, params=None, receiver_lookup=None, manual_matches=None,
                 company_names=None, company_keywords=None, date_from=None):
        """
        :param companies: {company_id: {'name': str, 'first_date': date|None}}
        :param lines: apuntes del universo hasta la fecha de corte (ver docstring
            del módulo); también los anteriores a ``date_from``, para emparejar
            documentos que cruzan el inicio del periodo
        :param date_from: inicio del periodo (opcional). Los grupos con todos sus
            apuntes antes de esa fecha no se detallan: suman en una línea por par
            "Diferencias anteriores al periodo".
        :param receiver_lookup: callable(company, kind, serie, number) -> list of
            {'move_name', 'state', 'partner_company' (int|None), 'partner_name'}
            para la regla 7 (comprobante en la otra empresa en cualquier estado).
        :param manual_matches: [{'id': int, 'line_ids': set, 'reason': str}]
        """
        self.companies = companies
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.receiver_lookup = receiver_lookup
        self.manual_matches = manual_matches or []
        self.company_names = company_names or {cid: data['name'] for cid, data in companies.items()}
        # Palabras con que las glosas mencionan a cada empresa (regla 13): de su
        # razón social y alias configurados.
        self.company_keywords = {
            cid: sorted(set(self.name_tokens(data.get('legal_name') or data['name'])
                            + [k.upper() for k in (company_keywords or {}).get(cid, [])]))
            for cid, data in companies.items()
        }
        self.date_from = date_from
        self.lines = [line for line in lines if line['company'] != line['partner_company']]
        self.lines_by_id = {line['id']: line for line in self.lines}
        self.used = set()
        self.groups = []

    # ------------------------------------------------------------------ #
    # Utilidades
    # ------------------------------------------------------------------ #

    def name(self, company):
        return self.company_names.get(company, str(company))

    def free(self, lines):
        return [line for line in lines if line['id'] not in self.used]

    def add_group(self, category, rule, lines, note='', extra=None):
        lines = [line for line in lines if line['id'] not in self.used]
        if not lines:
            return None
        group = Group(category, rule, lines, note, extra)
        self.used.update(line['id'] for line in lines)
        self.groups.append(group)
        return group

    @staticmethod
    def side(lines, company):
        return [line for line in lines if line['company'] == company]

    # ------------------------------------------------------------------ #
    # Ejecución
    # ------------------------------------------------------------------ #

    def run(self):
        self.balances = defaultdict(float)
        self.opening = defaultdict(float)
        self.pair_lines = defaultdict(list)
        for line in self.lines:
            key = pair_key(line['company'], line['partner_company'], line['block'])
            self.pair_lines[key].append(line)
            self.balances[(key, line['company'])] += line['balance']
            if self.date_from and line['date'] < self.date_from:
                self.opening[(key, line['company'])] += line['balance']

        self.rule_manual_matches()          # 14 (primero: la decisión del usuario prevalece)
        self.rule_fx()                       # 2
        for key, lines in self.pair_lines.items():
            self.rule_documents(key, lines)  # 3-8
        self.rule_no_effect()                # 9
        for key in list(self.pair_lines):
            self.rule_payments(key)                     # 10-12
        movements = self.build_movements()
        self.rule_triangular(movements)                 # 13
        self.rule_same_side(movements)                  # 13: las dos empresas del mismo lado
        self.rule_unmatched()                           # 15
        self.rule_combinations()                        # 16-17: pago más retención, uno contra varios
        self.rule_advances()                            # 18: anticipos y préstamos en varias partes
        self.rule_suggestions()                         # sugerencias (no emparejan)
        return self.summarize()

    # 14. Emparejamientos manuales -------------------------------------- #

    def rule_manual_matches(self):
        for match in self.manual_matches:
            lines = [self.lines_by_id[line_id] for line_id in match['line_ids'] if line_id in self.lines_by_id]
            if lines:
                # Categoría a la que vuelve si se deshace el emparejamiento.
                self.add_group('manual_match', 14, lines, note=match.get('reason') or '',
                               extra={'manual_match_id': match['id'],
                                      'original_category': self.unmatched_category(lines[0])})

    # 2. Diferencia de cambio automática -------------------------------- #

    def rule_fx(self):
        by_key = defaultdict(list)
        for line in self.lines:
            if line['is_fx_journal'] and line['id'] not in self.used:
                by_key[(pair_key(line['company'], line['partner_company'], line['block']), line['company'])].append(line)
        for (_key, _company), lines in by_key.items():
            self.add_group('fx', 2, lines, note=f'{len(lines)} apuntes del diario de diferencia de cambio',
                           extra={'aggregated': True})

    # 3-8. Comprobantes ------------------------------------------------- #

    def document_moves(self, lines):
        """{move_id: [lines]} de los comprobantes (ventas y compras) aún libres."""
        moves = defaultdict(list)
        for line in self.free(lines):
            if line['doc_kind'] and line['doc_number']:
                moves[line['move_id']].append(line)
        return moves

    def rule_documents(self, key, lines):
        params = self.params
        company_a, company_b, _block = key
        moves = self.document_moves(lines)
        issued = {}     # (issuer, receiver, kind, serie, number) -> move lines (ventas)
        received = {}   # idem para compras
        for move_lines in moves.values():
            first = move_lines[0]
            doc_key = (first['doc_kind'], first['doc_serie'], first['doc_number'])
            if first['move_type'].startswith('out_'):
                issued[(first['company'], first['partner_company'], *doc_key)] = move_lines
            else:
                received[(first['partner_company'], first['company'], *doc_key)] = move_lines

        # 3-4. Por número exacto.
        for doc_key in list(issued):
            if doc_key in received:
                self.classify_document_pair(issued.pop(doc_key), received.pop(doc_key))

        # 5. Serie distinta (mismo número, importe y moneda).
        self.match_documents(issued, received, rule=5, category='serie_diff',
                             same_number=True, days=None, tolerance=params['amount_tolerance'])
        # 6. Número distinto (mismo importe y moneda, fecha cercana).
        self.match_documents(issued, received, rule=6, category='number_diff',
                             same_number=False, days=params['number_days'], tolerance=params['amount_tolerance'])

        # 7-8. Sin par.
        for move_lines in issued.values():
            self.add_group('unregistered_receiver', 8, move_lines, note=self.document_note(move_lines, received_side=False))
        for move_lines in received.values():
            self.add_group('no_issuer', 8, move_lines, note=self.document_note(move_lines, received_side=True))

    def match_documents(self, issued, received, rule, category, same_number, days, tolerance):
        for doc_key in list(issued):
            sale = issued[doc_key]
            first = sale[0]
            best = None
            for purchase_key, purchase in received.items():
                other = purchase[0]
                if purchase_key[:3] != doc_key[:3] or other['move_currency'] != first['move_currency']:
                    continue
                if same_number and (purchase_key[4] != doc_key[4] or purchase_key[3] == doc_key[3]):
                    continue
                if not same_number and purchase_key[4] == doc_key[4]:
                    continue
                if abs(abs(other['doc_total']) - abs(first['doc_total'])) > tolerance:
                    continue
                gap = abs((other['date'] - first['date']).days)
                if days is not None and gap > days:
                    continue
                if best is None or gap < best[0]:
                    best = (gap, purchase_key)
            if best:
                purchase = received.pop(best[1])
                del issued[doc_key]
                note = f"{self.name(purchase[0]['company'])} lo registró como {purchase[0]['doc_serie']}-{purchase[0]['doc_number']}"
                match_category = category
                # Contraparte en 0 en las cuentas intercompany: no es un tema de serie
                # o número, el comprobante no está registrado con la otra empresa.
                if abs(sum(l['amount_currency'] for l in purchase)) <= tolerance < abs(sum(l['amount_currency'] for l in sale)):
                    match_category = 'unregistered_receiver'
                    note += ' con importe 0 en las cuentas intercompany'
                self.add_group(match_category, rule, sale + purchase, note=note,
                               extra={'counterpart_company': purchase[0]['company']})

    def classify_document_pair(self, sale, purchase):
        params = self.params
        lines = sale + purchase
        effect = sum(line['balance'] for line in lines)
        first, other = sale[0], purchase[0]
        same_currency_lines = {line['currency'] for line in lines}
        note = ''
        extra = {'counterpart_company': other['company']}
        if first['move_currency'] != other['move_currency']:
            category = 'currency_diff'
            note = f"{first['move_currency']} en {self.name(first['company'])}, {other['move_currency']} en {self.name(other['company'])}"
            # Aunque esté en otra moneda, si el efecto en soles es mínimo queda conciliado con la observación.
            extra['pending'] = abs(effect) > params['amount_tolerance']
        else:
            totals_equal = abs(abs(first['doc_total']) - abs(other['doc_total'])) <= params['document_total_tolerance']
            ic_currency = sum(line['amount_currency'] for line in lines) if len(same_currency_lines) == 1 else None
            if ic_currency is not None and abs(ic_currency) > params['document_total_tolerance']:
                if not totals_equal and abs(abs(first['doc_total']) - abs(other['doc_total'])) <= params['rounding_tolerance'] \
                        and abs(effect) <= params['rounding_tolerance']:
                    category = 'rounding'
                elif totals_equal:
                    category = 'advance_diff'
                    note = (f"Total {first['move_currency']} {abs(first['doc_total']):,.2f} en ambas; en cuentas IC "
                            f"{abs(sum(l['amount_currency'] for l in sale)):,.2f} vs {abs(sum(l['amount_currency'] for l in purchase)):,.2f}")
                else:
                    category = 'amount_diff'
                    note = f"Total {abs(first['doc_total']):,.2f} vs {abs(other['doc_total']):,.2f}"
            elif round(abs(effect), 2) == 0:
                category = 'matched'
            elif (first['date'].year, first['date'].month) != (other['date'].year, other['date'].month):
                category = 'period_diff'
                note = f"{first['date']:%m/%Y} en {self.name(first['company'])}, {other['date']:%m/%Y} en {self.name(other['company'])}"
            elif abs(effect) <= params['rounding_tolerance']:
                # Mismo importe en la moneda del documento: el efecto en soles es redondeo.
                category = 'rounding'
                note = f"Diferencia de redondeo S/ {effect:,.2f}"
            elif first['move_currency'] != 'PEN':
                # Mismo importe en la moneda del documento, distinto en soles.
                note = f"TC {self.rate(sale):.4f} en la venta, {self.rate(purchase):.4f} en la compra"
                base = abs(sum(line['balance'] for line in sale))
                if abs(effect) <= max(base * params['rate_diff_percent'] / 100.0, params['rate_diff_minimum']):
                    # Centavos sobre un importe grande: redondeo del tipo de cambio.
                    category = 'rounding'
                    note += f"; diferencia S/ {effect:,.2f} dentro de la tolerancia de tipo de cambio"
                else:
                    category = 'rate_diff'
            else:
                category = 'amount_diff'
        if category == 'rounding' and not note:
            note = f"Diferencia de redondeo S/ {effect:,.2f}"
        self.add_group(category, 4, lines, note=note, extra=extra)

    @staticmethod
    def rate(lines):
        amount = sum(abs(line['amount_currency']) for line in lines)
        return sum(abs(line['balance']) for line in lines) / amount if amount else 0.0

    def document_note(self, move_lines, received_side):
        first = move_lines[0]
        notes = []
        if not received_side and abs(first['doc_total']) < 0.005:
            notes.append('factura final con aplicación de anticipos (total 0)')
        counterpart = first['partner_company']
        if self.receiver_lookup and not received_side:
            for found in self.receiver_lookup(counterpart, first['doc_kind'], first['doc_serie'], first['doc_number']):
                if found['state'] == 'draft':
                    notes.append(f"registrada en borrador en {self.name(counterpart)} ({found['move_name']})")
                elif found['state'] == 'cancel':
                    notes.append(f"anulada en {self.name(counterpart)} ({found['move_name']})")
                elif found.get('partner_company') != first['company']:
                    notes.append(f"registrada en {self.name(counterpart)} con otro socio: {found.get('partner_name')} ({found['move_name']})")
        first_date = self.companies.get(counterpart, {}).get('first_date')
        if first_date and first['date'] < first_date:
            notes.append(f"anterior al inicio en Odoo de {self.name(counterpart)} ({first_date:%d/%m/%Y}): debería estar en su saldo de apertura")
        return '; '.join(notes)

    # 9. Anulado en la misma empresa ------------------------------------ #

    def rule_no_effect(self):
        tolerance = self.params['amount_tolerance']
        by_move = defaultdict(list)
        for line in self.lines:
            if line['id'] not in self.used:
                by_move[(line['move_id'], line['partner_company'], line['block'])].append(line)
        for (_move, _partner, _block), lines in by_move.items():
            if len(lines) > 1 and abs(sum(line['balance'] for line in lines)) <= tolerance \
                    and abs(sum(line['amount_currency'] for line in lines)) <= tolerance:
                self.add_group('no_effect', 9, lines, note='Las líneas del asiento con la otra empresa suman cero')
        # Provisión y su reversión.
        by_move = defaultdict(list)
        for line in self.lines:
            if line['id'] not in self.used:
                by_move[line['move_id']].append(line)
        for move_id, lines in list(by_move.items()):
            reversed_id = lines[0].get('reversed_move_id')
            if not reversed_id or reversed_id not in by_move:
                continue
            original = self.free(by_move[reversed_id])
            current = self.free(lines)
            for partner, block in {(l['partner_company'], l['block']) for l in current}:
                both = [l for l in current + original if l['partner_company'] == partner and l['block'] == block]
                if both and abs(sum(l['balance'] for l in both)) <= tolerance:
                    self.add_group('no_effect', 9, both, note='Asiento y su reversión')
        # Provisión y extorno sin vínculo: dos asientos manuales de la misma
        # empresa con la otra que se anulan en su moneda (el residuo en soles es
        # diferencia de cambio).
        manual = defaultdict(list)
        for movement in self.build_movements().values():
            for m in movement:
                if m['lines'][0]['journal_type'] == 'general' and not m['lines'][0]['doc_kind']:
                    manual[(m['company'], m['partner'], m['block'], m['currency'])].append(m)
        for items in manual.values():
            for index, first in enumerate(items):
                if not self.movement_free(first):
                    continue
                for second in items[index + 1:]:
                    if self.movement_free(second) and abs(first['amount'] + second['amount']) <= tolerance \
                            and abs((second['date'] - first['date']).days) <= 62:
                        residual = first['balance'] + second['balance']
                        self.add_group('no_effect' if abs(residual) <= tolerance else 'fx', 9,
                                       first['lines'] + second['lines'],
                                       note='Provisión y su extorno en la misma empresa'
                                            + ('' if abs(residual) <= tolerance else ' (diferencia de cambio)'))
                        break

    # 10-12. Pagos y movimientos ---------------------------------------- #

    def build_movements(self, lines=None, per_line=False):
        """Apuntes libres agrupados por asiento (o uno por apunte), par y bloque."""
        movements = defaultdict(list)
        by_move = defaultdict(list)
        for line in (self.lines if lines is None else lines):
            if line['id'] not in self.used:
                group_key = line['id'] if per_line else line['move_id']
                by_move[(group_key, line['company'], line['partner_company'], line['block'])].append(line)
        for (_group_key, company, partner, block), lines in by_move.items():
            move_id = lines[0]['move_id']
            currencies = {line['currency'] for line in lines}
            # Un movimiento en una sola moneda se compara en esa moneda; uno mixto, en soles.
            single_currency = len(currencies) == 1
            currency = currencies.pop() if single_currency else 'PEN'
            movements[pair_key(company, partner, block)].append({
                'lines': lines, 'company': company, 'partner': partner, 'block': block,
                'currency': currency, 'date': lines[0]['date'], 'move_id': move_id,
                'amount': sum(l['amount_currency'] if single_currency else l['balance'] for l in lines),
                'balance': sum(l['balance'] for l in lines),
                'label': ' '.join(filter(None, {lines[0]['label'] or '', lines[0]['ref'] or ''})),
            })
        for key in movements:
            movements[key].sort(key=lambda m: (m['date'], m['move_id']))
        return movements

    def movement_free(self, movement):
        return all(line['id'] not in self.used for line in movement['lines'])

    def rule_payments(self, key):
        params = self.params
        company_a, company_b, _block = key

        def sides(per_line):
            items = self.build_movements(self.pair_lines[key], per_line=per_line).get(key, [])
            return ([m for m in items if m['company'] == company_a],
                    [m for m in items if m['company'] == company_b])

        def same_currency(a, b):
            return a['currency'] == b['currency'] and abs(a['amount'] + b['amount']) <= params['amount_tolerance']

        def other_currency(a, b):
            limit = max(abs(a['balance']) * params['other_currency_percent'] / 100.0, params['other_currency_minimum'])
            return abs(a['balance'] + b['balance']) <= limit

        # 10. Mismo importe en la misma moneda: asiento contra asiento y luego
        # línea contra línea (un pago puede agrupar varias detracciones o
        # facturas en un mismo asiento).
        for per_line in (False, True):
            self.match_single(*sides(per_line), rule=10, days=params['payment_days'], compare=same_currency)
        # 11. Otra moneda: comparación en soles.
        for per_line in (False, True):
            self.match_single(*sides(per_line), rule=11, days=params['payment_days'], compare=other_currency)
        # 12. Pagos agrupados: suma de un asiento o de un día contra una o varias
        # líneas de la otra empresa (también un movimiento en otra moneda que
        # cuadra exacto en soles dentro del plazo de pagos agrupados).
        def exact_pen(a, b):
            return a['currency'] != b['currency'] and abs(a['balance'] + b['balance']) <= params['amount_tolerance']
        for per_line in (False, True):
            self.match_single(*sides(per_line), rule=12, days=params['grouped_days'], compare=exact_pen)
        for per_line in (False, True):
            side_a, side_b = sides(per_line)
            self.match_grouped(side_a, side_b, rule=12, days=params['grouped_days'])
            side_a, side_b = sides(per_line)
            self.match_grouped(side_b, side_a, rule=12, days=params['grouped_days'])

    def match_single(self, side_a, side_b, rule, days, compare, category='matched', note=''):
        for a in side_a:
            if not self.movement_free(a):
                continue
            best = None
            for b in side_b:
                if not self.movement_free(b):
                    continue
                gap = abs((a['date'] - b['date']).days)
                if gap > days or not compare(a, b):
                    continue
                score = (gap, abs(a['balance'] + b['balance']))
                if best is None or score < best[0]:
                    best = (score, b)
            if best:
                self.close_match([a, best[1]], rule, category, note)

    def match_grouped(self, side_a, side_b, rule, days):
        tolerance = self.params['amount_tolerance']
        by_day = defaultdict(list)
        for a in side_a:
            if self.movement_free(a):
                by_day[(a['date'], a['currency'])].append(a)
        for (day, currency), group_a in by_day.items():
            group_a = [a for a in group_a if self.movement_free(a)]
            if not group_a:
                continue
            total = sum(a['amount'] for a in group_a)
            candidates = [b for b in side_b if self.movement_free(b) and b['currency'] == currency
                          and abs((b['date'] - day).days) <= days]
            # Un movimiento de la otra empresa contra la suma del día.
            single = [b for b in candidates if abs(b['amount'] + total) <= tolerance]
            if single and len(group_a) > 1:
                self.close_match(group_a + [single[0]], rule, 'matched', 'Pagos agrupados')
                continue
            # Suma de un día de la otra empresa.
            by_day_b = defaultdict(list)
            for b in candidates:
                by_day_b[b['date']].append(b)
            for _day_b, group_b in sorted(by_day_b.items(), key=lambda item: abs((item[0] - day).days)):
                if (len(group_a) > 1 or len(group_b) > 1) and abs(sum(b['amount'] for b in group_b) + total) <= tolerance:
                    self.close_match(group_a + group_b, rule, 'matched', 'Pagos agrupados')
                    break

    def close_match(self, movements, rule, category='matched', note=''):
        """Empareja movimientos; el residuo en soles (tipos de cambio distintos o
        tolerancia) queda en su propio grupo de diferencia de cambio o redondeo
        para que el control siga en 0."""
        lines = [line for movement in movements for line in movement['lines']]
        residual = sum(line['balance'] for line in lines)
        currencies = {movement['currency'] for movement in movements}
        by_company = defaultdict(set)
        for movement in movements:
            by_company[movement['company']].add(movement['currency'])
        if category == 'matched' and len(by_company) == 2:
            (company_a, currencies_a), (company_b, currencies_b) = sorted(by_company.items())
            if currencies_a.isdisjoint(currencies_b):
                # Moneda distinta entre ambas empresas: se muestra aunque el efecto sea 0;
                # queda conciliado (el residuo es tipo de cambio).
                self.add_group('currency_diff', rule, lines, extra={'matched': True, 'pending': False}, note=(
                    f"{'/'.join(sorted(currencies_a))} en {self.name(company_a)}, "
                    f"{'/'.join(sorted(currencies_b))} en {self.name(company_b)}; "
                    f"diferencia S/ {residual:,.2f} por tipo de cambio"))
                return
        if category == 'matched' and abs(residual) > self.params['amount_tolerance']:
            residual_category = 'fx' if (currencies - {'PEN'} or rule == 11) else 'rounding'
            self.add_group(residual_category, rule, lines,
                           note=f"Emparejado (regla {rule}); diferencia S/ {residual:,.2f} por tipo de cambio o redondeo",
                           extra={'matched': True})
        else:
            self.add_group(category, rule, lines, note=note, extra={'matched': True})

    # 13. Compensación de 3 empresas ------------------------------------ #

    def rule_triangular(self, movements):
        params = self.params
        names = self.company_keywords
        # Candidatos: pagos o cobros (banco/caja) cuya glosa menciona a otra empresa.
        free = [m for items in movements.values() for m in items if self.movement_free(m)]
        by_company = defaultdict(list)
        for m in free:
            by_company[m['company']].append(m)
        for a in free:
            if not self.movement_free(a) or a['lines'][0]['journal_type'] not in ('bank', 'cash'):
                continue
            label = (a['label'] or '').upper()
            thirds = [cid for cid, tokens in names.items()
                      if cid not in (a['company'], a['partner']) and any(token in label for token in tokens)]
            for third in thirds:
                # Cobro de la tercera empresa (socio A o socio B), signo contrario.
                receipt = self.find_counter(by_company[third], a, {a['company'], a['partner']}, params['triangular_days'])
                # Reconocimiento de B frente a la tercera o frente a A.
                recognition = self.find_counter(by_company[a['partner']], a, {third, a['company']},
                                                params['triangular_days'], same_sign=True, exclude=receipt)
                if receipt and recognition:
                    note = (f"{self.name(a['company'])} pagó a {self.name(third)} por cuenta de {self.name(a['partner'])}")
                    lines = a['lines'] + receipt['lines'] + recognition['lines']
                    self.add_group('triangular', 13, lines, note=note, extra={'third_company': third})
                    break
                missing = [self.name(c) for c, found in ((third, receipt), (a['partner'], recognition)) if not found]
                self.add_group('triangular_incomplete', 13, a['lines'] + (receipt or recognition or {'lines': []})['lines'],
                               note=f"{self.name(a['company'])} pagó a {self.name(third)} por cuenta de "
                                    f"{self.name(a['partner'])}: falta registrar en {', '.join(missing)}",
                               extra={'third_company': third})
                break

    def find_counter(self, candidates, movement, partners, days, same_sign=False, exclude=None):
        tolerance = self.params['amount_tolerance']
        for other in candidates:
            if other is exclude or not self.movement_free(other) or other['partner'] not in partners:
                continue
            if other['currency'] != movement['currency'] or abs((other['date'] - movement['date']).days) > days:
                continue
            target = movement['amount'] if same_sign else -movement['amount']
            if abs(abs(other['amount']) - abs(movement['amount'])) <= tolerance and (other['amount'] > 0) == (target > 0):
                return other
        return None

    @staticmethod
    def name_tokens(name):
        """Palabras distintivas de una razón social (sin la forma societaria ni
        palabras comunes)."""
        name = (name or '').upper()
        stop = {'S.A.C.', 'SAC', 'E.I.R.L.', 'EIRL', 'S.R.L.', 'SRL', 'S.A.', 'INC', 'PERU', 'PERÚ', 'THE', 'LOS', 'LAS',
                'DEL', 'PROJECT', 'COMPAÑÍA', 'COMPANIA', 'MINERA', 'ENTERPRISES', 'RESOURCES', 'EXPORTACION',
                'SOLUCIONES', 'INGENIERIA', 'TRIUMPH'}
        tokens = [token for token in re.split(r'[^A-ZÁÉÍÓÚÑ0-9-]+', name) if len(token) >= 4 and token not in stop]
        if 'JE-AL' in name:
            tokens += ['JEAL', 'JE-AL', 'JE AL']
        return tokens

    # Las dos empresas registraron del mismo lado ------------------------ #

    def rule_same_side(self, movements):
        """El movimiento está en ambas empresas por el mismo importe y en sentido
        contrario, pero las dos usaron cuentas del mismo lado (p.ej. ambas la 122,
        o ambas la 42): cae en bloques opuestos del par. Se concilia con la
        observación de cuenta distinta; cada bloque lo explica con su parte."""
        params = self.params
        for key, items in movements.items():
            company_a, company_b, creditor = key
            other_items = movements.get((company_a, company_b, company_b if creditor == company_a else company_a), [])
            for side_company, other_company in ((company_a, company_b), (company_b, company_a)):
                mine = [m for m in items if m['company'] == side_company and self.movement_free(m)]
                theirs = [m for m in other_items if m['company'] == other_company and self.movement_free(m)]
                if not mine or not theirs:
                    continue
                for a in mine:
                    best = None
                    for b in theirs:
                        if not self.movement_free(b) or a['currency'] != b['currency'] \
                                or abs(a['amount'] + b['amount']) > params['amount_tolerance']:
                            continue
                        gap = abs((a['date'] - b['date']).days)
                        if gap <= params['grouped_days'] and (best is None or gap < best[0]):
                            best = (gap, b)
                    if best:
                        b = best[1]
                        side = 'por cobrar' if a['block'] == a['company'] else 'por pagar'
                        accounts = ' / '.join(
                            f"{self.name(m['company'])} en {', '.join(sorted({l['account_code'] for l in m['lines']}))}"
                            for m in sorted((a, b), key=lambda m: m['company']))
                        account_note = f"{accounts} (las dos {side})"
                        residual = a['balance'] + b['balance']
                        note = f"{self.account_text(accounts)}; las dos {side}"
                        if abs(residual) > params['amount_tolerance']:
                            note += f"; diferencia S/ {residual:,.2f} por tipo de cambio"
                        self.add_group('matched_account', 13, a['lines'] + b['lines'], note=note,
                                       extra={'pending': False, 'account_note': account_note, 'matched': True})

    # 15. Sin par -------------------------------------------------------- #

    def rule_unmatched(self):
        by_move = defaultdict(list)
        for line in self.lines:
            if line['id'] not in self.used:
                by_move[(line['move_id'], line['company'], line['partner_company'], line['block'])].append(line)
        for (_move, _company, _partner, _block), lines in by_move.items():
            first = lines[0]
            self.add_group(self.unmatched_category(first), 15, lines, note=self.unmatched_note(first, lines))

    @staticmethod
    def unmatched_category(line):
        journal = f"{line['journal_code']} {line['journal_name']}".upper()
        label = f"{line['label']} {line['ref']}".upper()
        if line['journal_type'] == 'general' and not line['doc_kind']:
            if re.search(r'DIF\w*\.?\s*(DE\s+)?CAMBIO|DIFERENCIA\s+(EN\s+)?(DE\s+)?(TIPO\s+DE\s+)?CAMBIO', label):
                return 'fx'
        if 'DETRAC' in journal:
            return 'detraction'
        if 'RETENC' in journal or line.get('doc_type_code') == '20':
            return 'retention'
        if 'APERT' in journal or (line['move_name'] or '').upper().startswith('APERT'):
            return 'opening'
        if line['journal_type'] in ('bank', 'cash'):
            return 'payment'
        if line['doc_kind']:
            return 'unregistered_receiver' if line['move_type'].startswith('out_') else 'no_issuer'
        return 'manual_entry'

    def unmatched_note(self, first, lines):
        notes = []
        counterpart = first['partner_company']
        first_date = self.companies.get(counterpart, {}).get('first_date')
        if first_date and first['date'] < first_date:
            notes.append(f"anterior al inicio en Odoo de {self.name(counterpart)} ({first_date:%d/%m/%Y})")
        if first['doc_kind'] and not first['doc_number']:
            notes.append('comprobante sin número (Referencia vacía o con otro formato)')
        if first['journal_type'] == 'general' and not first['doc_kind'] and 'REDONDEO' in f"{first['label']} {first['ref']}".upper():
            notes.append('ajuste por redondeo sin contrapartida en la otra empresa')
        return '; '.join(notes)

    # 16-18. Pendientes que se explican entre sí ------------------------- #

    def pending_items(self, categories=None):
        """{par: [partidas]}: grupos pendientes de una sola empresa en un solo par,
        los que las reglas 16-18 y las sugerencias pueden explicar entre sí."""
        items = defaultdict(list)
        for group in self.groups:
            if not group.is_pending() or (categories and group.category not in categories):
                continue
            keys = {pair_key(l['company'], l['partner_company'], l['block']) for l in group.lines}
            companies = {l['company'] for l in group.lines}
            if len(keys) != 1 or len(companies) != 1:
                continue
            key = keys.pop()
            items[key].append({
                'group': group, 'company': companies.pop(), 'key': key, 'category': group.category,
                'balance': sum(l['balance'] for l in group.lines), 'date': min(l['date'] for l in group.lines),
            })
        for values in items.values():
            values.sort(key=lambda item: (item['date'], item['group'].lines[0]['move_id']))
        return items

    def merge_items(self, items, rule, note):
        """Reemplaza los grupos pendientes de ``items`` por un solo grupo conciliado."""
        merged = {id(item['group']) for item in items}
        self.groups = [group for group in self.groups if id(group) not in merged]
        lines = [line for item in items for line in item['group'].lines]
        residual = sum(line['balance'] for line in lines)
        if abs(residual) > self.params['amount_tolerance']:
            note += f"; diferencia S/ {residual:,.2f}"
        group = Group('matched', rule, lines, note, {'matched': True, 'pending': False})
        self.groups.append(group)
        for item in items:
            item['merged'] = True
        return group

    @staticmethod
    def find_combination(item, candidates, tolerance, size_range=(2, 3)):
        """2 o 3 partidas de ``candidates`` (de signo contrario) cuya suma explica
        ``item``. La mejor: menos partidas, menor residuo, fechas más cercanas."""
        target = -item['balance']
        candidates = [c for c in candidates if c['balance'] * target > 0]
        best = None
        for size in size_range:
            for combo in combinations(candidates, size):
                residual = abs(sum(c['balance'] for c in combo) - target)
                if residual > tolerance:
                    continue
                score = (residual, max(abs((c['date'] - item['date']).days) for c in combo))
                if best is None or score < best[0]:
                    best = (score, combo)
            if best:
                return list(best[1])
        return None

    def rule_combinations(self):
        """16. Un pago es igual al pago de la otra empresa más la retención del 3%.
        17. Un pago o documento es igual a la suma de 2 o 3 partidas de la otra
        empresa del mismo par, de cualquier categoría, dentro del plazo de pagos
        agrupados."""
        params = self.params
        tolerance = params['combination_tolerance']
        for key, items in self.pending_items(COMBINABLE_CATEGORIES).items():
            for retention_pass in (True, False):
                for item in items:
                    if item.get('merged') or (retention_pass and item['category'] == 'retention'):
                        continue
                    candidates = sorted(
                        (other for other in items if not other.get('merged') and other['company'] != item['company']
                         and abs((other['date'] - item['date']).days) <= params['grouped_days']),
                        key=lambda other: abs((other['date'] - item['date']).days))[:MAX_CANDIDATES]
                    if retention_pass:
                        combo = self.find_retention(item, candidates, tolerance)
                        if combo:
                            self.merge_items([item] + combo, 16, f"Pago más retención {RETENTION_RATE:.0%}")
                        continue
                    combo = self.find_combination(item, candidates, tolerance)
                    if combo:
                        self.merge_items([item] + combo, 17, f"Pago agrupado: {len(combo) + 1} líneas")

    def find_retention(self, item, candidates, tolerance):
        """Pago + retención de la otra empresa que suman ``item``; la retención es
        el 3% del total."""
        total = abs(item['balance'])
        retentions = [c for c in candidates if c['category'] == 'retention'
                      and abs(abs(c['balance']) - total * RETENTION_RATE) <= tolerance]
        if not retentions:
            return None
        payments = [c for c in candidates if c['category'] != 'retention']
        for retention in retentions:
            combo = self.find_combination({**item, 'balance': item['balance'] + retention['balance']},
                                          payments, tolerance, size_range=(1,))
            if combo:
                return combo + [retention]
        return None

    @staticmethod
    def advance_key(group):
        """Clave de agrupación de un anticipo o préstamo: el comprobante que cita la
        glosa o, si no cita ninguno, el tipo (las glosas de cada empresa rara vez
        coinciden)."""
        first = group.lines[0]
        text = strip_accents(f"{first['label'] or ''} {first['ref'] or ''}".upper())
        match = ADVANCE_RE.search(text)
        if not match:
            return None
        documents = document_numbers(text)
        if documents:
            return documents[0]
        return 'Préstamo' if match.group(0) in ('PRESTAM', 'DESEMBOLS') else 'Anticipo'

    def rule_advances(self):
        """18. Anticipo o préstamo registrado en un solo asiento en una empresa y en
        varias partes en la otra: se suman todas las líneas de cada lado con la misma
        glosa (o el mismo comprobante citado). Si las sumas no cuadran, las líneas
        quedan pendientes con la marca "Anticipo aplicado parcialmente"."""
        tolerance = self.params['combination_tolerance']
        for key, items in self.pending_items(COMBINABLE_CATEGORIES).items():
            by_advance = defaultdict(list)
            for item in items:
                advance = self.advance_key(item['group'])
                if advance:
                    by_advance[advance].append(item)
            for advance, grouped in by_advance.items():
                companies = {item['company'] for item in grouped}
                if len(companies) < 2 or len(grouped) < 3:
                    continue
                count = {company: len([i for i in grouped if i['company'] == company]) for company in companies}
                detail = ' contra '.join(f"{count[c]} en {self.name(c)}" for c in sorted(companies))
                kind = advance if advance in ('Anticipo', 'Préstamo') else f"Anticipo {advance}"
                total = sum(item['balance'] for item in grouped)
                if abs(total) <= tolerance:
                    self.merge_items(grouped, 18, f"{kind} agrupado: {detail}")
                    continue
                sums = ', '.join(
                    f"{self.name(c)} S/ {sum(i['balance'] for i in grouped if i['company'] == c):,.2f}"
                    for c in sorted(companies))
                for item in grouped:
                    item['group'].extra['partial_advance'] = True
                    item['group'].note = '; '.join(filter(None, [
                        item['group'].note, f"{kind} aplicado parcialmente ({detail}; {sums})"]))

    def rule_suggestions(self):
        """Posible contraparte de una partida pendiente (no empareja): la glosa cita
        un comprobante de la otra empresa, o el monto difiere hasta el 2% y la fecha
        hasta 30 días."""
        params = self.params
        # Por par de empresas (los dos bloques): la contraparte puede haber usado una
        # cuenta del otro lado.
        by_pair = defaultdict(list)
        for key, items in self.pending_items().items():
            by_pair[key[:2]] += items
        # Comprobantes de las partidas pendientes (también las de las dos empresas).
        documents = defaultdict(list)
        for group in self.groups:
            if not group.is_pending():
                continue
            for line in group.lines:
                for number in {document_key(line['doc_serie'], line['doc_number']),
                               *document_numbers(line['move_name'] or '')} - {None}:
                    documents[(pair_key(line['company'], line['partner_company'], None)[:2], number)].append(
                        {'group': group, 'company': line['company'], 'balance': sum(l['balance'] for l in group.lines
                                                                                     if l['company'] == line['company'])})
        for pair, items in by_pair.items():
            for item in items:
                group = item['group']
                own = {number for line in group.lines for number in {
                    document_key(line['doc_serie'], line['doc_number']), *document_numbers(line['move_name'] or '')}}
                text = strip_accents(f"{group.lines[0]['label'] or ''} {group.lines[0]['ref'] or ''}".upper())
                found = None
                for number in set(document_numbers(text)) - own:
                    others = [o for o in documents.get((pair, number), [])
                              if o['company'] != item['company'] and o['group'] is not group]
                    if others:
                        found = (others[0], f"la glosa menciona {number}")
                        break
                if not found:
                    best = None
                    for other in items:
                        if other['company'] == item['company'] or other['balance'] * item['balance'] >= 0:
                            continue
                        largest = max(abs(other['balance']), abs(item['balance']))
                        percent = abs(other['balance'] + item['balance']) / largest * 100 if largest else 0.0
                        days = abs((other['date'] - item['date']).days)
                        if percent <= params['suggestion_percent'] and days <= params['suggestion_days'] \
                                and (best is None or (percent, days) < best[0]):
                            best = ((percent, days), other)
                    if best:
                        percent, days = best[0]
                        found = (best[1], f"el monto difiere {percent:.1f}% y la fecha {days} días")
                if found:
                    other, reason = found
                    first = next(l for l in other['group'].lines if l['company'] == other['company'])
                    group.extra['suggestion'] = other['group']
                    group.extra['suggestion_note'] = (
                        f"Posible contraparte: {first['move_name']} de {self.name(other['company'])} "
                        f"(S/ {other['balance']:,.2f}): {reason}")

    # Resumen ------------------------------------------------------------ #

    def summarize(self):
        """Devuelve (pares, detalle).

        pares: {(a, b, bloque): {'balance_a', 'balance_b', 'difference', 'opening_a', 'opening_b',
                                 'opening_difference', 'by_category', 'control', 'matched_count',
                                 'pending_count'}}
        detalle: lista de dicts, una por grupo y par en el que tiene efecto (con
        periodo: más una por par con las diferencias anteriores al periodo).
        """
        pairs = {}
        for key in self.pair_lines:
            company_a, company_b, _block = key
            balance_a = round(self.balances[(key, company_a)], 2)
            balance_b = round(self.balances[(key, company_b)], 2)
            opening_a = round(self.opening[(key, company_a)], 2)
            opening_b = round(self.opening[(key, company_b)], 2)
            pairs[key] = {
                'balance_a': balance_a, 'balance_b': balance_b,
                'difference': round(balance_a + balance_b, 2),
                'opening_a': opening_a, 'opening_b': opening_b,
                'opening_difference': round(opening_a + opening_b, 2),
                'by_category': defaultdict(float), 'matched_count': 0, 'pending_count': 0,
            }
        details = []
        prior = defaultdict(lambda: {'effect': 0.0, 'groups': 0, 'lines': 0})
        for group in self.groups:
            per_pair = defaultdict(list)
            for line in group.lines:
                per_pair[pair_key(line['company'], line['partner_company'], line['block'])].append(line)
            for key, lines in per_pair.items():
                pair = pairs[key]
                # Todo apunte anterior a la fecha desde va al arrastre, así el arrastre es
                # igual a la diferencia al inicio. Un grupo que cruza la fecha se detalla
                # en el periodo solo con el efecto de sus apuntes del periodo.
                before = [line for line in lines if self.date_from and line['date'] < self.date_from]
                if before:
                    prior_effect = sum(line['balance'] for line in before)
                    pair['by_category']['prior_period'] += prior_effect
                    prior[key]['effect'] += prior_effect
                    prior[key]['lines'] += len(before)
                    if group.is_pending():
                        prior[key]['groups'] += 1
                    if len(before) == len(lines):
                        continue
                effect = sum(line['balance'] for line in lines if line not in before)
                account_note = group.extra.get('account_note') or self.account_note(lines)
                category = 'matched_account' if group.category == 'matched' and account_note else group.category
                pair['by_category'][category] += effect
                pending = group.is_pending()
                if pending:
                    pair['pending_count'] += 1
                else:
                    pair['matched_count'] += 1
                if category == 'matched' and abs(effect) < 0.005:
                    continue
                note = group.note
                if category == 'matched_account' and not group.extra.get('account_note'):
                    note = '; '.join(filter(None, [self.account_text(account_note), note]))
                if before and abs(sum(line['balance'] for line in before)) >= 0.005:
                    note = '; '.join(filter(None, [note, (
                        f"S/ {sum(line['balance'] for line in before):,.2f} de apuntes anteriores al "
                        f"{self.date_from:%d/%m/%Y} van en el arrastre")]))
                details.append(self.detail(group, key, lines, effect, category=category, pending=pending,
                                           account_note=account_note, note=note))
        for key, values in prior.items():
            if abs(values['effect']) >= 0.005:
                details.append(self.prior_detail(key, values))
        for key, pair in pairs.items():
            pair['by_category'] = {cat: round(value, 2) for cat, value in pair['by_category'].items()}
            explained = sum(pair['by_category'].values())
            pair['control'] = round(pair['difference'] - explained, 2)
        return pairs, details

    @staticmethod
    def account_text(accounts):
        """Observación de un documento registrado en cuentas distintas."""
        return f"Documento en ambas empresas, en cuentas distintas ({accounts})"

    def account_note(self, lines):
        """Observación automática cuando las dos empresas usan cuentas de distinta
        familia (comercial / préstamo), p.ej. "EQ en 1212001 / OUTCALL en 4699001"."""
        by_company = defaultdict(list)
        for line in lines:
            by_company[line['company']].append(line)
        if len(by_company) != 2:
            return ''
        families = [{line.get('family') for line in company_lines} for company_lines in by_company.values()]
        if families[0] == families[1]:
            return ''
        return ' / '.join(
            f"{self.name(company)} en {', '.join(sorted({line['account_code'] for line in company_lines}))}"
            for company, company_lines in sorted(by_company.items()))

    def prior_detail(self, key, values):
        """Línea agregada de un par: diferencias de documentos anteriores al periodo."""
        company_a, company_b, _block = key
        effect = round(values['effect'], 2)
        return {
            'pair_key': key, 'category': 'prior_period', 'rule': 0,
            'company': company_a, 'counterpart_company': company_b,
            'line_ids': [], 'move_ids': [], 'move_name': '', 'counterpart_line_ids': [], 'counterpart_move_ids': [],
            'counterpart_move_name': '', 'doc_type': '', 'doc_number': '',
            'date': self.date_from - timedelta(days=1), 'counterpart_date': None,
            'currency': 'PEN', 'amount_currency': effect, 'amount_pen': effect,
            'counterpart_currency': '', 'counterpart_amount_currency': 0.0, 'counterpart_amount_pen': 0.0,
            'effect_pen': effect, 'account_code': '', 'label': '',
            'note': f"Diferencia al {self.date_from - timedelta(days=1):%d/%m/%Y}: {values['lines']} apuntes anteriores "
                    f"al periodo ({values['groups']} partidas pendientes)",
            'action_hint': CATEGORY_HINTS['prior_period'], 'line_count': values['lines'], 'aggregated': True,
            'manual_match_id': None, 'pending': False, 'account_note': '',
            'group_ref': None, 'suggestion_ref': None, 'suggestion_note': '', 'partial_advance': False,
            'review_key': f"{company_a}:prior:{company_b}:{key[2]}:{effect:.2f}",
        }

    def detail(self, group, key, lines, effect, category=None, pending=None, account_note='', note=None):
        companies = {line['company'] for line in lines}
        # El registro principal: el lado con más apuntes (o el emisor del comprobante).
        main_company = group.extra.get('main_company')
        if main_company not in companies:
            sales = [l for l in lines if l['move_type'].startswith('out_')]
            main_company = (sales or lines)[0]['company']
        own = [l for l in lines if l['company'] == main_company]
        other = [l for l in lines if l['company'] != main_company]
        if not other:
            # La contraparte está en el otro bloque del par (registrado del mismo
            # lado): se muestra como referencia; el efecto es solo el de este bloque.
            other = [l for l in group.lines if l['company'] in key[:2] and l['company'] != main_company]
        first = own[0]
        counterpart_first = other[0] if other else None
        currency = first['currency']
        return {
            'pair_key': key,
            'category': category or group.category,
            'pending': group.is_pending() if pending is None else pending,
            'account_note': account_note,
            'rule': group.rule,
            'company': main_company,
            'counterpart_company': key[1] if main_company == key[0] else key[0],
            'line_ids': [l['id'] for l in own],
            'move_ids': sorted({l['move_id'] for l in own}),
            'move_name': first['move_name'],
            'counterpart_line_ids': [l['id'] for l in other],
            'counterpart_move_ids': sorted({l['move_id'] for l in other}),
            'counterpart_move_name': counterpart_first['move_name'] if counterpart_first else '',
            'doc_type': first['doc_kind'] or '',
            'doc_number': f"{first['doc_serie']}-{first['doc_number']}" if first['doc_number'] else '',
            'date': first['date'],
            'counterpart_date': counterpart_first['date'] if counterpart_first else None,
            'currency': currency,
            'amount_currency': round(sum(l['amount_currency'] for l in own), 2),
            'amount_pen': round(sum(l['balance'] for l in own), 2),
            'counterpart_currency': counterpart_first['currency'] if counterpart_first else '',
            'counterpart_amount_currency': round(sum(l['amount_currency'] for l in other), 2) if other else 0.0,
            'counterpart_amount_pen': round(sum(l['balance'] for l in other), 2) if other else 0.0,
            'effect_pen': round(effect, 2),
            'account_code': first['account_code'],
            'label': first['label'] or first['ref'] or '',
            'note': group.note if note is None else note,
            'action_hint': CATEGORY_HINTS.get(category or group.category, ''),
            'line_count': len(lines),
            'aggregated': bool(group.extra.get('aggregated')),
            'manual_match_id': group.extra.get('manual_match_id'),
            # Sugerencia de contraparte (no empareja): referencia al grupo sugerido.
            'original_category': group.extra.get('original_category'),
            'group_ref': id(group),
            'suggestion_ref': id(group.extra['suggestion']) if group.extra.get('suggestion') else None,
            'suggestion_note': group.extra.get('suggestion_note', ''),
            'partial_advance': bool(group.extra.get('partial_advance')),
            'review_key': review_key(main_company, sorted({l['move_id'] for l in own}), sum(l['balance'] for l in own)),
        }


def review_key(company, move_ids, amount):
    """Huella de un registro para reconocer su revisión en otra ejecución: si el
    importe cambia, la huella ya no coincide y vuelve a pendiente. Los asientos
    van como hash (una línea agregada puede tener cientos)."""
    moves = hashlib.sha1(','.join(str(m) for m in sorted(move_ids)).encode()).hexdigest()[:16]
    return f"{company}:{moves}:{round(amount, 2):.2f}"
