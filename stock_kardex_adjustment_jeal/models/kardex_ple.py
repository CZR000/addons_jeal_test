# -*- coding: utf-8 -*-
"""Kardex con ajustes en los formatos SUNAT 13.1 (valorizado) y 12.1 (unidades
físicas): libro físico (Excel y PDF) y TXT del PLE, leídos de las líneas del
proceso (nota técnica 13.1/12.1, puntos 3 y 4)."""
import base64
import io
import re
from calendar import monthrange
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, format_amount, format_date

from .kardex_engine import ADJUSTMENT_ROWS, ROW_ADJ_COST, ROW_ADJ_FX, ROW_ADJ_PRICE, ROW_LAYER, ROW_MANUAL, ROW_OPENING

BOOK_131 = '131'
BOOK_121 = '121'
BOOK_CODES = {BOOK_131: '130100', BOOK_121: '120100'}
BOOK_TITLES = {
    BOOK_131: 'FORMATO 13.1: "REGISTRO DE INVENTARIO PERMANENTE VALORIZADO - '
              'DETALLE DEL INVENTARIO VALORIZADO"',
    BOOK_121: 'FORMATO 12.1: "REGISTRO DEL INVENTARIO PERMANENTE EN UNIDADES FÍSICAS - '
              'DETALLE DEL INVENTARIO PERMANENTE EN UNIDADES FÍSICAS"',
}
# Tabla 14 SUNAT - Método de valuación
VALUATION_METHOD = '1'  # Promedio ponderado
VALUATION_METHOD_NAME = 'PROMEDIO PONDERADO'
OPENING_OPERATION = '16'
DOCUMENT_REQUIRED_OPERATIONS = ('01', '02', '03', '04', '05', '06')
ADJUSTMENT_LABEL = 'Ajuste kardex'
# Tabla 6 SUNAT de las unidades estándar, si la unidad no tiene código propio
UOM_CODES = {
    'uom.product_uom_unit': 'NIU',
    'uom.product_uom_dozen': 'DZN',
    'uom.product_uom_kgm': 'KGM',
    'uom.product_uom_gram': 'GRM',
    'uom.product_uom_ton': 'TNE',
    'uom.product_uom_litre': 'LTR',
    'uom.product_uom_gal': 'GLL',
    'uom.product_uom_meter': 'MTR',
    'uom.product_uom_hour': 'HUR',
}


def _alnum(value, size=20):
    return re.sub(r'[^0-9A-Za-z]', '', value or '')[:size]


def _text(value, size):
    value = re.sub(r'[|\r\n\t]+', ' ', value or '').strip()
    return value[:size]


def _split_document(number):
    """'E001-00000073' -> ('E001', '00000073'). Si hay varios números
    ('1281-1282-1283') se toma el primero."""
    parts = [p for p in re.split(r'[-\s,;/]+', (number or '').strip()) if p]
    if len(parts) >= 2:
        return _alnum(parts[0]), _alnum(parts[1])
    if parts:
        return '0', _alnum(parts[0])
    return '', ''


def _num(value, digits):
    """Número del TXT: sin separador de miles; los ceros como '0.00'."""
    value = round(value or 0.0, digits)
    if not value:
        return '0.00'
    return '%.*f' % (digits, value)


class StockKardexAdjustment(models.Model):
    _inherit = 'stock.kardex.adjustment'

    ple_131_txt = fields.Binary(string='TXT PLE 13.1', readonly=True, attachment=True)
    ple_131_txt_name = fields.Char(readonly=True)
    ple_131_xlsx = fields.Binary(string='Libro 13.1 (Excel)', readonly=True, attachment=True)
    ple_131_xlsx_name = fields.Char(readonly=True)
    ple_131_pdf = fields.Binary(string='Libro 13.1 (PDF)', readonly=True, attachment=True)
    ple_131_pdf_name = fields.Char(readonly=True)
    ple_121_txt = fields.Binary(string='TXT PLE 12.1', readonly=True, attachment=True)
    ple_121_txt_name = fields.Char(readonly=True)
    ple_121_xlsx = fields.Binary(string='Libro 12.1 (Excel)', readonly=True, attachment=True)
    ple_121_xlsx_name = fields.Char(readonly=True)
    ple_121_pdf = fields.Binary(string='Libro 12.1 (PDF)', readonly=True, attachment=True)
    ple_121_pdf_name = fields.Char(readonly=True)
    ple_message = fields.Text(string='Validación de los libros', readonly=True)

    def _ple_clear_vals(self):
        vals = {'ple_message': False}
        for book in (BOOK_131, BOOK_121):
            for kind in ('txt', 'xlsx', 'pdf'):
                vals['ple_%s_%s' % (book, kind)] = False
                vals['ple_%s_%s_name' % (book, kind)] = False
        return vals

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_ple_131(self):
        return self._generate_ple(BOOK_131)

    def action_generate_ple_121(self):
        return self._generate_ple(BOOK_121)

    def _ple_check_ready(self):
        """Solo un mes completo y sin ajustes pendientes, para que el libro
        coincida con la contabilidad (3.1)."""
        self.ensure_one()
        last_day = monthrange(self.date_from.year, self.date_from.month)[1]
        if (self.date_from.day != 1 or self.date_to.year != self.date_from.year
                or self.date_to.month != self.date_from.month or self.date_to.day != last_day):
            raise UserError(_(
                'Los libros 12.1 y 13.1 se emiten por mes calendario: el proceso debe ir '
                'del primer al último día del mismo mes.'))
        if self.filter_product_ids or self.filter_category_ids:
            raise UserError(_(
                'Los libros 12.1 y 13.1 incluyen todas las existencias: quite los filtros '
                'de productos y categorías y vuelva a calcular.'))
        self._do_compute()
        if self.pending_count:
            raise UserError(_(
                'Hay %s ajuste(s) pendiente(s) de registrar. Registre los ajustes antes de '
                'emitir los libros para que coincidan con la contabilidad.', self.pending_count))

    def _generate_ple(self, book):
        self.ensure_one()
        self._ple_check_ready()
        sections, warnings = self._ple_sections(book)
        period = self.date_from.strftime('%Y%m')
        ruc = _alnum(self.company_id.vat, 11)
        txt = self._ple_txt(book, sections)
        txt_name = 'LE%s%s00%s00%s%s%s1.txt' % (
            ruc, period, BOOK_CODES[book], '1', '1' if txt else '0',
            '1' if self.company_id.currency_id.name == 'PEN' else '2')
        from .kardex_ple_xlsx import build_ple_workbook
        output = io.BytesIO()
        build_ple_workbook(self, book, sections, output)
        base_name = '%s_%s_%s' % ('13_1' if book == BOOK_131 else '12_1', ruc, period)
        pdf, _content_type = self.env['ir.actions.report'].with_context(
            ple_sections=sections)._render_qweb_pdf(
            'stock_kardex_adjustment_jeal.action_report_kardex_ple', self.ids,
            data={'book': book})
        checks = self._ple_checks(book, sections)
        message = '\n'.join(checks + warnings)
        self.write({
            'ple_%s_txt' % book: base64.b64encode((txt or '').encode('utf-8')),
            'ple_%s_txt_name' % book: txt_name,
            'ple_%s_xlsx' % book: base64.b64encode(output.getvalue()),
            'ple_%s_xlsx_name' % book: base_name + '.xlsx',
            'ple_%s_pdf' % book: base64.b64encode(pdf),
            'ple_%s_pdf_name' % book: base_name + '.pdf',
            'ple_message': message,
        })
        self.message_post(body=_('Libro %(book)s generado: %(files)s.',
                                 book='13.1' if book == BOOK_131 else '12.1',
                                 files=', '.join([txt_name, base_name + '.xlsx', base_name + '.pdf'])))
        return True

    # ------------------------------------------------------------------
    # Datos de la existencia
    # ------------------------------------------------------------------
    def _ple_establishment(self):
        partner = self.company_id.partner_id
        code = partner.annexed_establishment if 'annexed_establishment' in partner._fields else ''
        code = re.sub(r'\D', '', code or '')
        return code.zfill(4)[:7] if code else '0000'

    @api.model
    def _ple_stock_type(self, product):
        if 'stock_type' in product._fields and product.stock_type:
            return product.stock_type
        categ = product.categ_id
        while categ:
            if categ.kardex_stock_type:
                return categ.kardex_stock_type
            categ = categ.parent_id
        return False

    @api.model
    def _ple_uom_code(self, product):
        uom = product.uom_id
        code = uom.l10n_pe_edi_measure_unit_code if 'l10n_pe_edi_measure_unit_code' in uom._fields else False
        if not code:
            xmlid = uom.get_external_id().get(uom.id, '')
            code = UOM_CODES.get(xmlid, '')
        return (code or '')[:3]

    def _ple_product_info(self, product):
        catalog, code = '9', product.default_code or str(product.id)
        if ('stock_catalog' in product._fields and product.stock_catalog == '3'
                and product.barcode):
            catalog, code = '3', product.barcode
        unspsc = ''
        if 'unspsc_code_id' in product._fields and product.unspsc_code_id:
            unspsc = re.sub(r'\D', '', product.unspsc_code_id.code or '')
        return {
            'product': product,
            'catalog': catalog,
            'code': _text(code, 24),
            'unspsc_catalog': '1' if unspsc else '',
            'unspsc': unspsc,
            'stock_type': self._ple_stock_type(product) or '',
            'description': _text(product.name, 80),
            'uom': self._ple_uom_code(product),
            'method': VALUATION_METHOD,
        }

    # ------------------------------------------------------------------
    # Documento, CUO y correlativo de cada línea
    # ------------------------------------------------------------------
    def _ple_journal_document(self, move):
        """Ajustes y asientos manuales: tipo 00, serie = código del diario y
        número = número del asiento sin el prefijo (3.2)."""
        name = move.name or ''
        prefix = move.journal_id.code or ''
        rest = name[len(prefix):] if prefix and name.startswith(prefix) else name
        return '00', _alnum(prefix) or '0', _alnum(rest) or '0'

    def _ple_invoice(self, stock_move):
        lines = stock_move.purchase_line_id.invoice_lines or stock_move.sale_line_id.invoice_lines
        return lines.move_id.filtered(lambda m: m.state == 'posted').sorted('invoice_date')[:1]

    def _ple_stock_document(self, stock_move, operation, row_date):
        """Documento de un movimiento de almacén: el de traslado del albarán
        (si se registró), si no el comprobante de la compra o venta, si no la
        guía; la fecha es la del comprobante cuando cae en el período."""
        picking = stock_move.picking_id
        invoice = self._ple_invoice(stock_move)
        doc_date = row_date
        if invoice and invoice.invoice_date and invoice.invoice_date <= self.date_to:
            doc_date = invoice.invoice_date
        if picking and 'serie_transfer_document' in picking._fields \
                and picking.serie_transfer_document and picking.number_transfer_document:
            doc_type = picking.transfer_document_type_id.code \
                if picking.transfer_document_type_id else ''
            if not doc_type:
                doc_type = invoice.l10n_latam_document_type_id.code if invoice else '09'
            # Varias guías en el mismo albarán ('1281-1282-…'): la primera
            number = _alnum(re.split(r'[-\s,;/]+', picking.number_transfer_document.strip())[0])
            if operation in DOCUMENT_REQUIRED_OPERATIONS and doc_type in ('', '00'):
                doc_type = '09'
            return doc_date, doc_type or '09', _alnum(picking.serie_transfer_document) or '0', \
                number or '0', True
        if invoice:
            ref = (invoice.serie_correlative if 'serie_correlative' in invoice._fields else '') \
                or (invoice.ref if invoice.move_type.startswith('in_') else invoice.name)
            serie, number = _split_document(ref)
            if serie and number:
                return doc_date, invoice.l10n_latam_document_type_id.code or '01', serie, number, True
        if picking and 'picking_number' in picking._fields and picking.picking_number:
            serie, number = _split_document(picking.picking_number)
            if serie and number:
                return doc_date, '09', serie, number, True
        # Sin documento: la referencia interna del albarán
        reference = picking.name or stock_move.reference or ''
        match = re.match(r'^(.*?)(\d+)$', reference.strip())
        serie = _alnum(match.group(1)) if match else _alnum(reference)
        number = match.group(2) if match else '0'
        doc_type = '09' if operation in DOCUMENT_REQUIRED_OPERATIONS else '00'
        return row_date, doc_type, serie or '0', number or '0', False

    @staticmethod
    def _ple_cuo(move):
        return _alnum(move.name, 40) if move else ''

    def _ple_correlatives(self, moves):
        """Correlativo de cada apunte (campo 3): el del libro diario si existe
        (ple_correlative), si no 'M' + posición del apunte en el asiento."""
        result = {}
        if not moves:
            return result
        lines = self.env['account.move.line'].sudo().search(
            [('move_id', 'in', moves.ids)], order='move_id, id')
        has_ple = 'ple_correlative' in lines._fields
        position = defaultdict(int)
        for line in lines:
            position[line.move_id.id] += 1
            correlative = line.ple_correlative if has_ple else ''
            if not correlative or correlative[:1] not in ('A', 'M', 'C') or not 2 <= len(correlative) <= 10:
                correlative = 'M%s' % str(position[line.move_id.id]).zfill(9)
            result[(line.move_id.id, line.product_id.id, line.account_id.id)] = correlative
            result.setdefault((line.move_id.id, line.product_id.id, None), correlative)
        return result

    # ------------------------------------------------------------------
    # Secciones por existencia
    # ------------------------------------------------------------------
    def _ple_sections(self, book):
        """Una sección por existencia con sus líneas en el orden del kardex."""
        self.ensure_one()
        rows = self.row_ids.sorted('sequence')
        moves = rows.account_move_id | rows.adj_move_id
        correlatives = self._ple_correlatives(moves)
        period = self.date_from.strftime('%Y%m00')
        establishment = self._ple_establishment()
        rows_by_product = defaultdict(list)
        for row in rows:
            rows_by_product[row.product_id].append(row)
        sections, missing_type, missing_uom, no_document = [], [], [], []
        for product, product_rows in rows_by_product.items():
            info = self._ple_product_info(product)
            if not info['stock_type']:
                missing_type.append(product.display_name)
            if not info['uom']:
                missing_uom.append('%s (%s)' % (product.display_name, product.uom_id.name))
            lines = []
            for row in product_rows:
                line = self._ple_line(row, book, correlatives, no_document)
                if line:
                    lines.append(line)
            if book == BOOK_121 and len(lines) == 1 and not lines[0]['bal_qty']:
                continue  # Solo valor: no mueve unidades
            totals = defaultdict(float)
            for line in lines:
                if line['kind'] == ROW_OPENING:
                    continue
                for key in ('in_qty', 'in_total', 'out_qty', 'out_total'):
                    totals[key] += line[key]
            last = lines[-1]
            sections.append(dict(
                info, period=period, establishment=establishment, lines=lines,
                totals=dict(totals), closing_qty=last['bal_qty'], closing_value=last['bal_total'],
                account=product_rows[0].account_id))
        errors = []
        if missing_type:
            errors.append(_(
                'Falta el tipo de existencia (tabla 5) de: %s. Configúrelo en la categoría '
                '(Tipo de existencia (tabla 5)) o en el producto.', ', '.join(sorted(missing_type))))
        if missing_uom:
            errors.append(_(
                'Falta el código SUNAT (tabla 6) de la unidad de medida de: %s.',
                ', '.join(sorted(missing_uom))))
        if errors:
            raise UserError('\n'.join(errors))
        warnings = []
        if no_document:
            warnings.append(_(
                'Movimientos sin documento de traslado ni comprobante (se usó la referencia '
                'del albarán): %s.', ', '.join(sorted(set(no_document)))))
        return sections, warnings

    def _ple_line(self, row, book, correlatives, no_document):
        kind = row.row_type
        if book == BOOK_121 and kind not in (ROW_OPENING, ROW_LAYER):
            return None
        if book == BOOK_121 and kind == ROW_LAYER and not (row.in_qty or row.out_qty):
            return None
        line = {
            'kind': kind,
            'row': row,
            'date': row.date,
            'doc_date': row.date,
            'operation': row.operation_type or '99',
            'in_qty': row.in_qty, 'in_total': row.in_value,
            'out_qty': row.out_qty, 'out_total': row.out_value,
            'bal_qty': row.bal_qty, 'bal_total': row.bal_value,
            'is_adjustment': kind in ADJUSTMENT_ROWS,
            'note': row.note or '',
            'reference': row.reference or '',
        }
        if kind == ROW_OPENING:
            line.update({
                'cuo': 'SI%s' % self.date_from.strftime('%Y%m'),
                'correlative': 'A000000001',
                'doc_date': self.date_from,
                'doc_type': '00', 'serie': '0', 'number': '0',
                'operation': OPENING_OPERATION,
                'reference': _('SALDO INICIAL'),
            })
        elif kind in ADJUSTMENT_ROWS + (ROW_MANUAL,):
            move = row.adj_move_id if kind != ROW_MANUAL else row.account_move_id
            doc_type, serie, number = self._ple_journal_document(move)
            line.update({
                'cuo': self._ple_cuo(move),
                'correlative': self._ple_line_correlative(correlatives, move, row),
                'doc_type': doc_type, 'serie': serie, 'number': number,
                'operation': '99',
                'move_name': move.name or '',
            })
            if kind != ROW_MANUAL:
                line['note'] = self._ple_adjustment_note(row)
                line['reference'] = '%s %s' % (ADJUSTMENT_LABEL, row.reference or '')
        else:
            stock_move = row.layer_id.stock_move_id
            move = row.account_move_id
            if stock_move:
                doc_date, doc_type, serie, number, found = self._ple_stock_document(
                    stock_move, line['operation'], row.date)
                if not found:
                    no_document.append(stock_move.picking_id.name or stock_move.reference or '')
            else:
                doc_date = row.date
                doc_type, serie, number = self._ple_journal_document(move) if move else ('00', '0', '0')
            line.update({
                'cuo': self._ple_cuo(move) or 'SVL%s' % row.layer_id.id,
                'correlative': self._ple_line_correlative(correlatives, move, row) if move else 'M000000001',
                'doc_date': doc_date, 'doc_type': doc_type, 'serie': serie, 'number': number,
                'move_name': move.name or '',
            })
        line['in_unit'] = line['in_total'] / line['in_qty'] if line['in_qty'] else 0.0
        line['out_unit'] = line['out_total'] / line['out_qty'] if line['out_qty'] else 0.0
        line['bal_unit'] = line['bal_total'] / line['bal_qty'] if line['bal_qty'] else 0.0
        return line

    @staticmethod
    def _ple_line_correlative(correlatives, move, row):
        if not move:
            return 'M000000001'
        return (correlatives.get((move.id, row.product_id.id, row.account_id.id))
                or correlatives.get((move.id, row.product_id.id, None))
                or 'M000000001')

    def _ple_adjustment_note(self, row):
        if row.row_type == ROW_ADJ_FX:
            return _('%(label)s TC: factura %(inv)s / recepción %(rec)s. %(note)s',
                     label=ADJUSTMENT_LABEL, inv=row.tc_invoice, rec=row.tc_receipt,
                     note=row.note or '')
        if row.row_type == ROW_ADJ_PRICE:
            return _('%(label)s precio. %(note)s', label=ADJUSTMENT_LABEL, note=row.note or '')
        if row.row_type == ROW_ADJ_COST and row.adj_type == 'cost':
            return _('%(label)s costo promedio: costo recalculado %(recalc)s',
                     label=ADJUSTMENT_LABEL,
                     recalc=format_amount(self.env, row.recalc_value, self.currency_id))
        return _('%(label)s %(type)s. %(note)s', label=ADJUSTMENT_LABEL,
                 type=dict(row._fields['adj_type'].selection).get(row.adj_type, '').lower(),
                 note=row.note or '')

    # ------------------------------------------------------------------
    # TXT del PLE (3.3 y 4)
    # ------------------------------------------------------------------
    def _ple_txt(self, book, sections):
        qty_digits = min(8, max(2, self.env['decimal.precision'].precision_get('Product Unit of Measure')))
        out = []
        for section in sections:
            for line in section['lines']:
                head = [
                    section['period'], line['cuo'], line['correlative'],
                    section['establishment'], section['catalog'], section['stock_type'],
                    section['code'], section['unspsc_catalog'], section['unspsc'],
                    line['doc_date'].strftime('%d/%m/%Y'), line['doc_type'],
                    line['serie'], line['number'], line['operation'],
                    section['description'], section['uom'],
                ]
                opening = line['kind'] == ROW_OPENING
                if book == BOOK_121:
                    in_qty = line['bal_qty'] if opening else line['in_qty']
                    fields_ = head + [_num(in_qty, 2), _num(-line['out_qty'], 2), '1']
                else:
                    in_qty = line['bal_qty'] if opening else line['in_qty']
                    in_total = line['bal_total'] if opening else line['in_total']
                    in_unit = line['bal_unit'] if opening else line['in_unit']
                    fields_ = head + [
                        section['method'],
                        _num(in_qty, qty_digits), _num(in_unit, 8), _num(in_total, 2),
                        _num(-line['out_qty'], qty_digits), _num(line['out_unit'], 8),
                        _num(-line['out_total'], 2),
                        _num(line['bal_qty'], qty_digits), _num(line['bal_unit'], 8),
                        _num(line['bal_total'], 2),
                        '1',
                    ]
                out.append('|'.join(fields_) + '|')
        return '\r\n'.join(out) + ('\r\n' if out else '')

    # ------------------------------------------------------------------
    # Validación contra la contabilidad (criterios 3 y 4)
    # ------------------------------------------------------------------
    def _ple_checks(self, book, sections):
        currency = self.currency_id
        messages = []
        if book == BOOK_131:
            balances = self._accounting_balances()
            total = sum(s['closing_value'] for s in sections)
            accounting = 0.0
            differences = []
            for section in sections:
                balance = balances.get((section['account'].id, section['product'].id), 0.0)
                accounting += balance
                if not currency.is_zero(section['closing_value'] - balance):
                    differences.append(_(
                        '%(product)s: libro %(book)s, contabilidad %(acc)s',
                        product=section['code'],
                        book=format_amount(self.env, section['closing_value'], currency),
                        acc=format_amount(self.env, balance, currency)))
            messages.append(_(
                'Libro 13.1 al %(date)s: %(count)s existencias, saldo final %(total)s; saldo '
                'contable por producto en sus cuentas de valoración %(acc)s.',
                date=format_date(self.env, self.date_to), count=len(sections),
                total=format_amount(self.env, total, currency),
                acc=format_amount(self.env, accounting, currency)))
            if differences:
                messages.append(_('Diferencias por producto:\n%s', '\n'.join(differences)))
            else:
                messages.append(_('El saldo final de cada existencia es igual a su saldo contable.'))
        else:
            summary = {s.product_id.id: s.closing_qty for s in self.summary_ids}
            differences = [
                '%s: 12.1 %s, 13.1 %s' % (s['code'], s['closing_qty'], summary.get(s['product'].id))
                for s in sections
                if float_compare(s['closing_qty'], summary.get(s['product'].id, 0.0),
                                 precision_rounding=s['product'].uom_id.rounding) != 0
            ]
            messages.append(_(
                'Libro 12.1 al %(date)s: %(count)s existencias con unidades.\n%(qty)s',
                date=format_date(self.env, self.date_to), count=len(sections),
                qty='\n'.join('%s: %s %s' % (s['code'], round(s['closing_qty'], 4), s['uom'])
                              for s in sections)))
            if differences:
                messages.append(_('Diferencias de unidades con el 13.1:\n%s', '\n'.join(differences)))
            else:
                messages.append(_('Las unidades al cierre coinciden con las del 13.1.'))
        return messages


class ReportKardexPle(models.AbstractModel):
    _name = 'report.stock_kardex_adjustment_jeal.report_kardex_ple'
    _description = 'Libro 12.1 / 13.1 desde el ajuste del kardex'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['stock.kardex.adjustment'].browse(docids)
        book = (data or {}).get('book') or BOOK_131
        sections = self.env.context.get('ple_sections')
        if sections is None:
            sections = docs[:1]._ple_sections(book)[0] if docs else []
        return {
            'doc_ids': docids,
            'doc_model': 'stock.kardex.adjustment',
            'docs': docs,
            'book': book,
            'title': BOOK_TITLES[book],
            'sections': sections,
            'method_name': VALUATION_METHOD_NAME,
        }
