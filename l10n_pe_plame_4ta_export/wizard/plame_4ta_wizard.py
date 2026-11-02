# -*- coding: utf-8 -*-
import base64
import calendar
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PlameCuartaWizard(models.TransientModel):
    _name = 'l10n.pe.plame.4ta.wizard'
    _description = 'Wizard de exportación PLAME 4ta Categoría (.ps4)'

    # --- Filtros ---
    period_month = fields.Selection(
        selection=[
            ('01', 'Enero'), ('02', 'Febrero'), ('03', 'Marzo'),
            ('04', 'Abril'), ('05', 'Mayo'), ('06', 'Junio'),
            ('07', 'Julio'), ('08', 'Agosto'), ('09', 'Septiembre'),
            ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
        ],
        string='Mes',
        required=True,
        default=lambda self: fields.Date.today().strftime('%m'),
    )
    period_year = fields.Selection(
        selection='_get_year_selection',
        string='Año',
        required=True,
        default=lambda self: str(fields.Date.today().year),
    )
    document_type = fields.Selection(
        selection=[
            ('R', 'Recibo por Honorarios'),
            ('D', 'Dieta de Directorio'),
        ],
        string='Tipo de Comprobante',
        required=True,
        default='R',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto / Prestador',
        required=False,
        help='Si se deja vacío, se incluirán todos los prestadores del período.',
        domain="[('vat', '!=', False)]",
    )

    # --- Campos de salida (invisibles hasta generar) ---
    file_data = fields.Binary(string='Archivo .ps4', readonly=True)
    file_name = fields.Char(string='Nombre del archivo', readonly=True)

    # ==========================================================
    # Helpers
    # ==========================================================
    @api.model
    def _get_year_selection(self):
        current_year = fields.Date.today().year
        return [(str(y), str(y)) for y in range(current_year - 5, current_year + 1)]

    def _get_period_dates(self):
        """Devuelve (date_from, date_to) del mes/año elegido."""
        year = int(self.period_year)
        month = int(self.period_month)
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    def _get_document_type_code(self):
        """Código SUNAT del tipo de documento según selección del wizard."""
        return '02' if self.document_type == 'R' else '00'

    def _format_amount(self, amount):
        """Monto: entero sin decimales, si tiene decimales muestra 2."""
        if amount == int(amount):
            return str(int(amount))
        return "{:.2f}".format(amount)

    def _format_date(self, d):
        """Fecha DD/MM/AAAA o vacío si es None."""
        return d.strftime('%d/%m/%Y') if d else ''

    def _split_document_number(self, doc_number):
        """Separa 'E001-154' en ('E001', '154'). Sin padding."""
        if not doc_number or '-' not in doc_number:
            return '', ''
        parts = doc_number.split('-', 1)
        serie = parts[0].strip()
        numero = parts[1].strip().lstrip('0') or '0'
        return serie, numero

    def _get_payment_date(self, move):
        """Fecha del primer pago desde invoice_payments_widget.
        Se usa el widget porque cubre tanto account.payment formales como
        conciliaciones contra asientos manuales (ej. caja chica).
        """
        import json
        from datetime import datetime
        
        if not move.invoice_payments_widget:
            return False
        
        widget = move.invoice_payments_widget
        if isinstance(widget, str):
            try:
                widget = json.loads(widget)
            except json.JSONDecodeError:
                return False
        
        content = widget.get('content') if isinstance(widget, dict) else None
        if not content:
            return False
        
        payment_date = content[0].get('date')
        if not payment_date:
            return False
        
        if isinstance(payment_date, str):
            return datetime.strptime(payment_date, '%Y-%m-%d').date()
        return payment_date

    # ==========================================================
    # Búsqueda de facturas
    # ==========================================================
    def _search_moves(self):
        date_from, date_to = self._get_period_dates()
        doc_type_code = self._get_document_type_code()
    
        domain = [
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['paid', 'in_payment', 'partial']),
            ('l10n_latam_document_type_id.code', '=', doc_type_code),
        ]
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        
        moves = self.env['account.move'].search(domain, order='invoice_date, name')
        
        # Filtrar por fecha de pago dentro del periodo (criterio SUNAT: principio del percibido)
        result = self.env['account.move']
        for move in moves:
            payment_date = self._get_payment_date(move)
            if payment_date and date_from <= payment_date <= date_to:
                result |= move
        return result

    # ==========================================================
    # Construcción de líneas .ps4
    # ==========================================================
    def _build_line(self, move):
        """Construye una línea del archivo .ps4 con 10 campos."""
        # 1. Tipo de Documento de Identidad (fijo 06 = RUC)
        tipo_doc = '06'

        # 2. Número de Documento (RUC del partner de la factura)
        ruc = (move.partner_id.vat or '').strip()

        # 3. Tipo de Comprobante
        tipo_comp = self.document_type

        # 4 y 5. Serie y Número
        if self.document_type == 'R':
            serie, numero = self._split_document_number(move.ref or '')
        else:
            serie, numero = '', ''

        # 6. Monto Total del Servicio
        monto = self._format_amount(move.amount_untaxed)

        # 7. Fecha de Emisión
        fecha_emision = self._format_date(move.invoice_date) if self.document_type == 'R' else ''

        # 8. Fecha de Pago
        payment_date = self._get_payment_date(move)
        fecha_pago = self._format_date(payment_date)

        # 9. Indicador de Retención (RTA)
        retencion = '1' if move.amount_tax > 0 else '0'

        # 10. Convenio Doble Imposición (opcional, vacío por defecto)
        convenio = ''

        fields_list = [
            tipo_doc, ruc, tipo_comp, serie, numero,
            monto, fecha_emision, fecha_pago, retencion, convenio
        ]
        return '|'.join(fields_list)

    # ==========================================================
    # Validaciones
    # ==========================================================
    def _validate_company(self):
        company_vat = (self.env.company.vat or '').strip()
        if not company_vat:
            raise UserError(_(
                'La compañía "%(name)s" no tiene RUC configurado.',
                name=self.env.company.name,
            ))
        if len(company_vat) != 11 or not company_vat.isdigit():
            raise UserError(_(
                'El RUC de la compañía "%(name)s" no es válido (debe tener 11 dígitos).',
                name=self.env.company.name,
            ))

    def _validate_moves_partners(self, moves):
        """Valida que todos los partners de las facturas tengan RUC válido."""
        invalid = []
        for m in moves:
            vat = (m.partner_id.vat or '').strip()
            if not vat or len(vat) != 11 or not vat.isdigit():
                invalid.append('- %s (Factura: %s)' % (m.partner_id.name, m.name))
        if invalid:
            raise UserError(_(
                'Los siguientes contactos no tienen un RUC válido de 11 dígitos:\n\n%(list)s',
                list='\n'.join(invalid),
            ))

    # ==========================================================
    # Acción principal
    # ==========================================================
    def action_generate(self):
        self.ensure_one()
        self._validate_company()

        moves = self._search_moves()
        if not moves:
            raise UserError(_(
                'No se encontraron registros para los filtros seleccionados.'
            ))

        self._validate_moves_partners(moves)

        lines = [self._build_line(m) for m in moves]
        content = '\r\n'.join(lines) + '\r\n'
        content_bytes = content.encode('ISO-8859-1', errors='replace')

        file_name = 'RH_%s_%s%s.ps4' % (
            self.env.company.vat.strip(),
            self.period_year,
            self.period_month,
        )

        self.write({
            'file_data': base64.b64encode(content_bytes),
            'file_name': file_name,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n.pe.plame.4ta.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
