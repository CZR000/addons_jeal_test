# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    # ------------------------------------------------------------------
    # Helper para vistas
    # ------------------------------------------------------------------
    has_only_sunat_expenses = fields.Boolean(
        string='Solo gastos SUNAT',
        compute='_compute_has_only_sunat_expenses',
        help='True cuando todos los gastos del reporte tienen tipo de '
             'documento SUNAT informado. Se usa en la vista para ocultar '
             'el botón "Registrar en asiento contable" cuando corresponde.',
    )

    @api.depends(
        'expense_line_ids',
        'expense_line_ids.l10n_latam_document_type_id',
    )
    def _compute_has_only_sunat_expenses(self):
        for sheet in self:
            lines = sheet.expense_line_ids
            sheet.has_only_sunat_expenses = bool(lines) and all(
                e.l10n_latam_document_type_id for e in lines
            )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains(
        'expense_line_ids', 'expense_line_ids.l10n_latam_document_type_id',
    )
    def _check_no_mixed_sunat(self):
        """Prohíbe reportes de gastos que mezclan gastos SUNAT (con
        ``l10n_latam_document_type_id``) con gastos no-SUNAT (sin él).
        """
        for sheet in self:
            lines = sheet.expense_line_ids
            if not lines:
                continue
            with_doc = lines.filtered(lambda e: e.l10n_latam_document_type_id)
            without_doc = lines - with_doc
            if with_doc and without_doc:
                raise ValidationError(_(
                    'El reporte de gastos "%(name)s" mezcla gastos con '
                    'comprobante SUNAT y gastos sin comprobante SUNAT. '
                    'Sepárelos en dos reportes distintos.',
                    name=sheet.name,
                ))

    # ------------------------------------------------------------------
    # Aprobación — override
    # ------------------------------------------------------------------
    def _is_sunat_sheet(self):
        """Un reporte es "SUNAT" cuando todos sus gastos tienen
        ``l10n_latam_document_type_id``.
        """
        self.ensure_one()
        lines = self.expense_line_ids
        return bool(lines) and all(
            e.l10n_latam_document_type_id for e in lines
        )

    def action_approve_expense_sheets(self):
        """CORRECCIÓN B — Supresión del asiento nativo duplicado.

        Al aprobar un sheet SUNAT, el flujo nativo generaría un
        ``account.move`` con partner = empleado y montos descompuestos
        vía ``price_include``. Nuestro módulo genera su propia factura
        de proveedor SUNAT — tener ambas es doble contabilización.

        Estrategia:
          - Para sheets NO SUNAT: llamar al ``super()`` intacto.
          - Para sheets SUNAT: pasar un flag por contexto que le indica
            al nativo que no genere su asiento, y luego generar nuestra
            factura SUNAT. La transición de estado (submit → approve)
            la hace el ``super()`` igual.

        El flag ``no_expense_moves`` se lee en ``_prepare_bills_vals``
        del override — Odoo nativo no lo usa; es específico de este
        módulo para saltarse la generación de asiento sin duplicar
        toda la lógica de cambio de estado.
        """
        sunat = self.filtered(lambda s: s._is_sunat_sheet())
        other = self - sunat

        result = True

        # Sheets no-SUNAT: flujo nativo completo, sin cambios.
        if other:
            result = super(HrExpenseSheet, other).action_approve_expense_sheets()

        # Sheets SUNAT: aprobar SIN que el nativo cree el asiento
        # duplicado, y generar nuestra factura.
        if sunat:
            sunat._check_currency_matches_company()
            # Contexto para señalizar al override de _prepare_bills_vals
            # que en este flujo NO se debe delegar en la creación nativa.
            sunat_ctx = sunat.with_context(hr_expense_extension_sunat=True)
            result = super(HrExpenseSheet, sunat_ctx).action_approve_expense_sheets()
            for sheet in sunat:
                sheet._generate_sunat_bills()

        return result

    def _prepare_bills_vals(self):
        """Override — bloquea la creación del asiento nativo cuando el
        contexto indica que se trata de un flujo SUNAT.

        Odoo nativo llama a este método durante la aprobación para
        armar los vals de las facturas/asientos del sheet. Al devolver
        una lista vacía en modo SUNAT, ningún asiento nativo se crea,
        y nuestro ``_generate_sunat_bills`` toma el control.
        """
        if self.env.context.get('hr_expense_extension_sunat'):
            return []
        return super()._prepare_bills_vals()

    def action_sheet_move_post(self):
        """Suprime la generación del asiento nativo también si se
        invoca este botón para un sheet SUNAT (protección extra: la
        vista ya oculta el botón vía has_only_sunat_expenses).
        """
        sunat_sheets = self.filtered(lambda s: s._is_sunat_sheet())
        other_sheets = self - sunat_sheets
        if sunat_sheets:
            for sheet in sunat_sheets:
                sheet.message_post(body=_(
                    'Se omitió la generación del asiento nativo — el '
                    'reporte usa comprobantes SUNAT y las facturas ya '
                    'fueron creadas en la aprobación.',
                ))
        if other_sheets:
            return super(
                HrExpenseSheet, other_sheets
            ).action_sheet_move_post()
        return True

    # ------------------------------------------------------------------
    # Helpers de generación de facturas
    # ------------------------------------------------------------------
    def _check_currency_matches_company(self):
        """Validación bloqueante — multi-moneda queda fuera de alcance."""
        for sheet in self:
            company_currency = sheet.company_id.currency_id
            for expense in sheet.expense_line_ids:
                if expense.currency_id and expense.currency_id != company_currency:
                    raise UserError(_(
                        'El gasto "%(expense)s" está en moneda %(cur)s pero la '
                        'compañía usa %(company_cur)s. La generación de '
                        'facturas multi-moneda está fuera del alcance actual '
                        'del módulo.',
                        expense=expense.name or expense.display_name,
                        cur=expense.currency_id.name,
                        company_cur=company_currency.name,
                    ))

    def _group_expenses_for_bills(self):
        """Agrupa los gastos SUNAT del sheet por
        (vendor_id, doc_type, serie, número).
        """
        self.ensure_one()
        grouped = defaultdict(lambda: self.env['hr.expense'])
        for expense in self.expense_line_ids:
            key = (
                expense.vendor_id.id,
                expense.l10n_latam_document_type_id.id,
                expense.document_serie or '',
                expense.document_number or '',
            )
            grouped[key] |= expense
        return grouped

    def _check_bill_not_already_registered(self, expenses_group):
        """Verifica que no exista ya un ``account.move`` con el mismo
        comprobante para el mismo proveedor (excluyendo canceladas).
        """
        first = expenses_group[:1]
        number = f'{first.document_serie}-{first.document_number}'
        existing = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('partner_id', '=', first.vendor_id.id),
            (
                'l10n_latam_document_type_id',
                '=',
                first.l10n_latam_document_type_id.id,
            ),
            ('l10n_latam_document_number', '=', number),
            ('state', '!=', 'cancel'),
            ('move_type', 'in', ('in_invoice', 'in_refund')),
        ], limit=1)
        if existing:
            raise UserError(_(
                'Ya existe la factura de proveedor %(name)s '
                '(%(number)s) para el proveedor %(vendor)s. '
                'Cancele o elimine el duplicado antes de aprobar este '
                'reporte.',
                name=existing.display_name,
                number=number,
                vendor=first.vendor_id.display_name,
            ))

    def _prepare_bill_from_expenses(self, expenses_group):
        """Prepara los ``vals`` para crear una ``account.move``
        (in_invoice) a partir de un grupo de gastos que comparten
        el mismo comprobante.
        """
        self.ensure_one()
        first = expenses_group[:1]
        journal = self._get_expense_journal(first)

        invoice_line_vals = []
        for expense in expenses_group:
            if expense.use_multiple_lines and expense.line_ids:
                for line in expense.line_ids:
                    invoice_line_vals.append(
                        (0, 0, line._prepare_move_line_vals())
                    )
            else:
                invoice_line_vals.append(
                    (0, 0, self._prepare_move_line_from_expense(expense))
                )

        vals = {
            'move_type': 'in_invoice',
            'company_id': self.company_id.id,
            'partner_id': first.vendor_id.id,
            'invoice_date': first.date,
            'date': first.date,
            'journal_id': journal.id,
            'currency_id': (
                first.currency_id.id or self.company_id.currency_id.id
            ),
            'ref': f'{first.document_serie}-{first.document_number}',
            'invoice_origin': self.name,
            'expense_sheet_id': self.id,
            'l10n_latam_document_type_id': (
                first.l10n_latam_document_type_id.id
            ),
            'l10n_latam_document_number': (
                f'{first.document_serie}-{first.document_number}'
            ),
            'igv_assignment_id': first.igv_assignment_id.id,
            'ecpn_id': first.ecpn_id.id,
            'merchant_id': first.merchant_id.id,
            'invoice_line_ids': invoice_line_vals,
        }
        return vals

    def _prepare_move_line_from_expense(self, expense):
        """CORRECCIÓN A — Leer los valores ya calculados del gasto.

        El flujo nativo de hr.expense ya resolvió:
          - ``total_amount`` = total tal como lo ve el empleado (S/ 200)
          - ``tax_ids`` = impuesto con su flag ``price_include``
          - la descomposición base + IGV según ``price_include``

        No recalculamos: pasamos ``price_unit = total_amount / quantity``
        y confiamos en que el motor de facturas de Odoo aplicará
        ``price_include`` igual que lo hizo el gasto. Así la factura
        cierra en el mismo total del gasto (200), no en 236.

        Fallback de partner:
        ``vendor_id`` del gasto → ``work_contact_id`` del empleado →
        ``False``.
        """
        partner = (
            expense.vendor_id
            or expense.employee_id.work_contact_id
            or self.env['res.partner']
        )
        qty = expense.quantity or 1.0
        # total_amount refleja lo que el usuario ve en el gasto,
        # respetando price_include. Dividimos por cantidad para obtener
        # el price_unit que el motor de facturas usará.
        price_unit = (expense.total_amount or 0.0) / qty
        return {
            'name': expense.name or (
                expense.product_id.display_name
                if expense.product_id else ''
            ),
            'product_id': expense.product_id.id,
            'quantity': qty,
            'price_unit': price_unit,
            'account_id': expense.account_id.id,
            'tax_ids': [(6, 0, expense.tax_ids.ids)],
            'analytic_distribution': expense.analytic_distribution or False,
            'partner_id': partner.id if partner else False,
        }

    def _get_expense_journal(self, expense):
        """Diario de compras por defecto de la compañía."""
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_(
                'No se encontró un diario de compras para la compañía '
                '"%(company)s". Configúrelo antes de aprobar el reporte.',
                company=self.company_id.display_name,
            ))
        return journal

    def _generate_sunat_bills(self):
        """Crea, publica y vincula al reporte una factura de proveedor
        por cada grupo de comprobante.
        """
        self.ensure_one()
        AccountMove = self.env['account.move']
        groups = self._group_expenses_for_bills()
        for _key, expenses_group in groups.items():
            self._check_bill_not_already_registered(expenses_group)
            vals = self._prepare_bill_from_expenses(expenses_group)
            move = AccountMove.create(vals)
            move.action_post()
            self.message_post(
                body=_(
                    'Se generó la factura de proveedor %(link)s a partir '
                    'de %(count)s gasto(s).',
                    link=move._get_html_link(),
                    count=len(expenses_group),
                )
            )

    # ------------------------------------------------------------------
    # Cancelación
    # ------------------------------------------------------------------
    def action_reset_expense_sheets(self):
        """Al reiniciar / cancelar el reporte, se cancelan las facturas
        asociadas con ``button_cancel`` (nunca ``unlink``).
        """
        for sheet in self:
            bills = sheet.account_move_ids.filtered(
                lambda m: m.state != 'cancel'
            )
            if bills:
                bills.button_cancel()
                sheet.message_post(body=_(
                    'Se cancelaron %(count)s factura(s) de proveedor '
                    'asociada(s) al reporte.',
                    count=len(bills),
                ))
        return super().action_reset_expense_sheets()
