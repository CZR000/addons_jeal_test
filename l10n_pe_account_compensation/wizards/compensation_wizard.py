# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class CompensationWizard(models.TransientModel):
    _name = 'l10n_pe.compensation.wizard'
    _description = 'Wizard de Compensación de Cuentas'

    # -------------------------------------------------------------------------
    # Campos base
    # -------------------------------------------------------------------------
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Factura origen',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one(
        related='move_id.partner_id',
        readonly=True,
    )
    company_id = fields.Many2one(
        related='move_id.company_id',
        readonly=True,
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='move_id.currency_id',
        string='Moneda',
        readonly=True,
    )
    origin_type = fields.Selection(
        selection=[
            ('sale', 'Venta (busca compras)'),
            ('purchase', 'Compra (busca ventas)'),
        ],
        compute='_compute_origin_type',
        string='Tipo de origen',
    )
    move_residual_currency = fields.Monetary(
        related='move_id.amount_residual',
        currency_field='currency_id',
        string='Saldo pendiente origen',
        readonly=True,
    )
    # Residual del origen en moneda local, tomado exactamente de la línea AR/AP
    # de la factura (sin recalcular por TC). Evita pérdida de precisión.
    origin_residual_local = fields.Monetary(
        compute='_compute_origin_residual_local',
        currency_field='company_currency_id',
        string='Saldo pendiente origen (local)',
    )
    # TC efectivo del origen: residual_local / residual_cur.
    # Solo informativo — para valorizar se usa la proporción exacta.
    origin_rate = fields.Float(
        compute='_compute_origin_residual_local',
        digits=(12, 6),
        string='TC del origen',
    )

    # -------------------------------------------------------------------------
    # Configuración del asiento
    # -------------------------------------------------------------------------
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario',
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    date = fields.Date(
        string='Fecha contable',
        required=True,
        default=fields.Date.context_today,
    )
    currency_rate = fields.Float(
        string='Tipo de cambio',
        digits=(12, 6),
        required=True,
        default=1.0,
        help='Tipo de cambio informativo del wizard (moneda local / '
             'moneda extranjera). No se usa para valorizar líneas: cada '
             'factura se valoriza con su propio TC original.',
    )

    # -------------------------------------------------------------------------
    # Líneas y totales
    # -------------------------------------------------------------------------
    line_ids = fields.One2many(
        comodel_name='l10n_pe.compensation.wizard.line',
        inverse_name='wizard_id',
        string='Facturas a compensar',
    )
    total_currency = fields.Monetary(
        compute='_compute_totals',
        currency_field='currency_id',
        string='Total a compensar',
    )
    pending_to_compensate = fields.Monetary(
        compute='_compute_totals',
        currency_field='currency_id',
        string='Saldo pendiente a compensar',
        help='Diferencia entre el saldo de la factura origen y el total a compensar, '
             'en la moneda de la factura.',
    )
    pending_is_negative = fields.Boolean(
        compute='_compute_totals',
        string='Saldo negativo',
        help='Indica que el total a compensar supera el saldo de la factura origen.',
    )
    is_full_compensation = fields.Boolean(
        compute='_compute_totals',
        string='Compensación total',
        help='True cuando el total a compensar iguala el saldo pendiente del origen.',
    )
    exchange_diff = fields.Monetary(
        compute='_compute_totals',
        currency_field='company_currency_id',
        string='Diferencia de tipo de cambio',
    )
    show_exchange_diff = fields.Boolean(
        compute='_compute_totals',
        string='Mostrar diferencia de TC',
    )
    amount_gap_currency = fields.Monetary(
        compute='_compute_totals',
        currency_field='currency_id',
        string='Diferencia de montos (moneda)',
        help='Diferencia entre el saldo total de las contrapartes seleccionadas y el '
             'monto a compensar. Solo aplica en modo "Enviar diferencia a:" para elevar '
             'la contraparte a su saldo total.',
    )
    amount_gap_local = fields.Monetary(
        compute='_compute_totals',
        currency_field='company_currency_id',
        string='Ajuste por diferencia de montos',
        help='Diferencia de montos valorizada al TC de las contrapartes.',
    )
    has_amount_gap = fields.Boolean(
        compute='_compute_totals',
        string='Hay diferencia de montos',
        help='Indica si hay margen entre lo compensado y el saldo total de las CPs.',
    )
    gap_exceeds_threshold = fields.Boolean(
        compute='_compute_totals',
        string='Gap supera umbral',
        help='True cuando el gap de montos supera el umbral permitido (1 unidad '
             'en la moneda de la factura). En ese caso, la opción "Enviar '
             'diferencia a:" queda oculta.',
    )
    gap_threshold_warning = fields.Char(
        compute='_compute_totals',
        string='Mensaje de umbral',
    )

    # -------------------------------------------------------------------------
    # Tratamiento del desbalance
    # -------------------------------------------------------------------------
    imbalance_treatment = fields.Selection(
        selection=[
            ('exchange_diff', 'Enviar diferencia a:'),
            ('leave_pending', 'Dejar como saldo pendiente'),
        ],
        string='Tratamiento del desbalance',
        help='- Enviar diferencia a: eleva la contraparte a su saldo total y '
             'absorbe el ajuste en la cuenta elegida (cierra ambas facturas).\n'
             '- Dejar como saldo pendiente: solo se compensa hasta el saldo del '
             'origen; el residual de la contraparte queda vivo.',
    )
    exchange_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cuenta de ajuste',
        domain="[('company_ids', 'in', company_id), "
               "('account_type', 'in', ('income', 'income_other', 'expense', 'expense_other'))]",
        help='Cuenta contable donde se registra el ajuste por diferencia de montos '
             '(los centavos que hacen que la contraparte cierre al 100%).',
    )
    show_imbalance_treatment = fields.Boolean(
        compute='_compute_show_imbalance_treatment',
        string='Mostrar selector de tratamiento',
    )

    @api.depends('has_amount_gap', 'gap_exceeds_threshold')
    def _compute_show_imbalance_treatment(self):
        for wiz in self:
            wiz.show_imbalance_treatment = wiz.has_amount_gap

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------
    @api.depends('move_id.move_type')
    def _compute_origin_type(self):
        for wiz in self:
            if wiz.move_id.move_type == 'out_invoice':
                wiz.origin_type = 'sale'
            elif wiz.move_id.move_type == 'in_invoice':
                wiz.origin_type = 'purchase'
            else:
                wiz.origin_type = False

    @api.depends('move_id')
    def _compute_origin_residual_local(self):
        """Toma el residual local directamente de la línea AR/AP del origen,
        sin recalcular por TC. Así preservamos el rate exacto de la factura
        y evitamos que Odoo genere un AED automático al reconciliar."""
        for wiz in self:
            move = wiz.move_id
            if not move:
                wiz.origin_residual_local = 0.0
                wiz.origin_rate = 1.0
                continue
            ar_ap_lines = move.line_ids.filtered(
                lambda l: l.account_id.account_type in (
                    'asset_receivable', 'liability_payable'
                )
            )
            if not ar_ap_lines:
                wiz.origin_residual_local = 0.0
                wiz.origin_rate = 1.0
                continue
            # Sumar TODAS las cuotas (facturas con término de pago fraccionado
            # tienen una línea AR/AP por vencimiento).
            residual_local = sum(abs(l.amount_residual) for l in ar_ap_lines)
            residual_cur = sum(
                abs(l.amount_residual_currency) for l in ar_ap_lines
            ) or move.amount_residual
            wiz.origin_residual_local = residual_local
            wiz.origin_rate = (residual_local / residual_cur) if residual_cur else 1.0
    
    @api.depends('line_ids.selected', 'line_ids.amount_to_compensate',
                 'line_ids.amount_residual', 'line_ids.amount_residual_local',
                 'currency_rate', 'imbalance_treatment',
                 'move_id.amount_residual', 'origin_residual_local')
    def _compute_totals(self):
        for wiz in self:
            selected = wiz.line_ids.filtered('selected')
            currency = wiz.currency_id
            company_currency = wiz.company_currency_id

            # 1. Total a compensar (moneda de la factura)
            total_cur = sum(selected.mapped('amount_to_compensate'))
            wiz.total_currency = total_cur

            # 2. Saldo pendiente a compensar (misma moneda)
            pending = wiz.move_id.amount_residual - total_cur
            pending = currency.round(pending) if currency else pending
            if currency and currency.is_zero(pending):
                pending = 0.0
            wiz.pending_to_compensate = pending
            wiz.pending_is_negative = bool(currency) and currency.compare_amounts(pending, 0.0) < 0
            wiz.is_full_compensation = (
                bool(currency)
                and total_cur > 0
                and currency.is_zero(pending)
            )

            # 3. Diferencia de montos entre CPs seleccionadas y lo compensado
            cp_residual_total = sum(selected.mapped('amount_residual'))
            gap = cp_residual_total - total_cur
            gap = currency.round(gap) if currency else gap
            if currency and currency.is_zero(gap):
                gap = 0.0
            if gap < 0:
                gap = 0.0
            wiz.amount_gap_currency = gap
            wiz.has_amount_gap = bool(currency) and not currency.is_zero(gap)

            # 4. Cálculo del ajuste por diferencia de montos en moneda local,
            # usando el MISMO helper que el asiento (proporción exacta contra
            # el residual local de la línea AR/AP de cada CP).
            if wiz.has_amount_gap:
                counterpart_local_total = sum(
                    wiz._get_line_local_amount(line, line.amount_residual)
                    for line in selected
                )
                unelevated_local = sum(
                    wiz._get_line_local_amount(line, line.amount_to_compensate)
                    for line in selected
                )
                wiz.amount_gap_local = counterpart_local_total - unelevated_local
            else:
                wiz.amount_gap_local = 0.0

            # 5. Diferencia de tipo de cambio (moneda local).
            # Simulamos el balance del asiento: origen + CPs (elevadas o no) +
            # línea de ajuste (si aplica). El residuo que queda es la dif TC.
            if currency and currency != company_currency and selected:
                use_full_cp = (
                    wiz.imbalance_treatment == 'exchange_diff'
                    and wiz.has_amount_gap
                )
                # Lado CPs (residual completo si eleva, si no lo compensable)
                cp_local = sum(
                    wiz._get_line_local_amount(
                        line,
                        line.amount_residual if use_full_cp else line.amount_to_compensate,
                    )
                    for line in selected
                )
                # Lado origen (proporción exacta contra su residual local)
                origin_local = wiz._get_origin_local_amount(total_cur)
                # Línea de ajuste (si eleva)
                adj_local = wiz.amount_gap_local if use_full_cp else 0.0
                # Balance: origen absorbe una posición y CPs la otra
                # (sumamos como magnitudes, la dif TC es lo que sobra)
                diff = cp_local - origin_local - adj_local
                wiz.exchange_diff = abs(diff)
                wiz.show_exchange_diff = not company_currency.is_zero(diff)
            else:
                wiz.exchange_diff = 0.0
                wiz.show_exchange_diff = False

            # 6. Umbral del gap
            threshold = 1.0
            wiz.gap_exceeds_threshold = wiz.has_amount_gap and gap > threshold
            if wiz.gap_exceeds_threshold:
                symbol = currency.symbol or currency.name if currency else ''
                wiz.gap_threshold_warning = _(
                    'El ajuste (%(gap)s) supera el máximo permitido '
                    '(%(threshold)s %(symbol)s). Solo se puede dejar como '
                    'saldo pendiente.'
                ) % {
                    'gap': ('%s %s' % (gap, symbol)).strip(),
                    'threshold': '%.2f' % threshold,
                    'symbol': symbol,
                }
            else:
                wiz.gap_threshold_warning = False

    # -------------------------------------------------------------------------
    # Helpers de valorización (proporción exacta contra línea AR/AP)
    # -------------------------------------------------------------------------
    def _get_line_local_amount(self, line, amount_cur):
        """Devuelve el monto en moneda local proporcional al residual local
        de la línea AR/AP de la CP. Cuando amount_cur == residual completo,
        devuelve el residual local exacto — sin recalcular por TC — para que
        la reconciliación posterior no genere AED por diferencia de decimales."""
        company_currency = self.company_currency_id
        if not line.amount_residual:
            return 0.0
        # Si compensamos el 100% del residual, devolvemos el local exacto
        if self.currency_id.compare_amounts(amount_cur, line.amount_residual) == 0:
            return line.amount_residual_local
        # Prorrateo exacto (mismo TC efectivo que la factura)
        return company_currency.round(
            line.amount_residual_local * amount_cur / line.amount_residual
        )

    def _get_origin_local_amount(self, amount_cur):
        """Igual que _get_line_local_amount pero para la factura origen."""
        company_currency = self.company_currency_id
        residual_cur = self.move_id.amount_residual
        residual_local = self.origin_residual_local
        if not residual_cur:
            return 0.0
        if self.currency_id.compare_amounts(amount_cur, residual_cur) == 0:
            return residual_local
        return company_currency.round(
            residual_local * amount_cur / residual_cur
        )

    # -------------------------------------------------------------------------
    # Onchange
    # -------------------------------------------------------------------------
    @api.onchange('date')
    def _onchange_date(self):
        if not self.date or not self.move_id:
            return
        company = self.company_id
        if self.currency_id == company.currency_id:
            self.currency_rate = 1.0
        else:
            self.currency_rate = self.env['res.currency']._get_conversion_rate(
                from_currency=self.currency_id,
                to_currency=company.currency_id,
                company=company,
                date=self.date,
            )

    @api.onchange('imbalance_treatment')
    def _onchange_imbalance_treatment(self):
        if self.imbalance_treatment != 'exchange_diff':
            self.exchange_account_id = False

    @api.onchange('gap_exceeds_threshold')
    def _onchange_gap_exceeds_threshold(self):
        if self.gap_exceeds_threshold:
            self.imbalance_treatment = 'leave_pending'
            self.exchange_account_id = False
        
    # -------------------------------------------------------------------------
    # Carga de contrapartes
    # -------------------------------------------------------------------------
    def load_counterparts(self):
        self.ensure_one()
        move = self.move_id
        company = move.company_id

        counterpart_type = 'in_invoice' if move.move_type == 'out_invoice' else 'out_invoice'
        counterparts = self.env['account.move'].search([
            ('move_type', '=', counterpart_type),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('partner_id', '=', move.partner_id.id),
            ('company_id', '=', company.id),
            ('currency_id', '=', move.currency_id.id),
            ('amount_residual', '>', 0),
        ], order='invoice_date, id')

        WizardLine = self.env['l10n_pe.compensation.wizard.line']
        for cp in counterparts:
            # Tomar TODAS las líneas AR/AP (una por cuota del término de pago)
            # y sumarlas para obtener el residual total en ambas monedas.
            ar_ap_lines = cp.line_ids.filtered(
                lambda l: l.account_id.account_type in (
                    'asset_receivable', 'liability_payable'
                )
            )
            if not ar_ap_lines:
                continue
            residual_cur = sum(
                abs(l.amount_residual_currency) for l in ar_ap_lines
            ) or cp.amount_residual
            residual_local = sum(abs(l.amount_residual) for l in ar_ap_lines)
            cp_rate = (residual_local / residual_cur) if residual_cur else 1.0

            WizardLine.create({
                'wizard_id': self.id,
                'invoice_id': cp.id,
                'currency_id': cp.currency_id.id,
                'amount_residual': residual_cur,
                'amount_residual_local': residual_local,
                'invoice_rate': cp_rate,
                'selected': False,
                'amount_to_compensate': 0.0,
            })

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        move_id = vals.get('move_id') or self.env.context.get('active_id')
        if not move_id:
            return vals

        move = self.env['account.move'].browse(move_id)
        if not move.exists():
            return vals

        if move.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(_(
                'La compensación solo aplica en facturas de cliente o proveedor.'
            ))
        if move.state != 'posted':
            raise UserError(_('La factura debe estar publicada.'))
        if move.payment_state not in ('not_paid', 'partial'):
            raise UserError(_(
                'La factura debe estar sin pagar o pagada parcialmente.'
            ))
        if move.currency_id.is_zero(move.amount_residual):
            raise UserError(_('La factura no tiene saldo pendiente.'))

        company = move.company_id
        self._check_configuration(company)

        vals.update({
            'move_id': move.id,
            'journal_id': company.compensation_journal_id.id,
        })
        return vals

    @api.model
    def _check_configuration(self, company):
        missing = []
        if not company.compensation_journal_id:
            missing.append(_('Diario de compensación'))
        if not company.compensation_exchange_gain_account_id:
            missing.append(_('Cuenta de ganancia por diferencia de cambio'))
        if not company.compensation_exchange_loss_account_id:
            missing.append(_('Cuenta de pérdida por diferencia de cambio'))
        if missing:
            raise UserError(_(
                'Faltan configurar en Contabilidad → Ajustes:\n- %s'
            ) % '\n- '.join(missing))

    # -------------------------------------------------------------------------
    # Acción principal
    # -------------------------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        selected = self.line_ids.filtered('selected')
        self._validate_before_confirm(selected)

        move_vals = self._prepare_compensation_move(selected)

        line_cmds = move_vals.pop('line_ids', [])
        compensated_ids = move_vals.pop('compensated_invoice_ids', [])

        AccountMove = self.env['account.move'].with_context(
            check_move_validity=False,
            tracking_disable=True,
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            mail_notrack=True,
        )
        new_move = AccountMove.create(move_vals)

        line_vals_list = []
        for cmd in line_cmds:
            if isinstance(cmd, (list, tuple)) and len(cmd) >= 3 and cmd[0] == 0:
                vals = dict(cmd[2])
                vals['move_id'] = new_move.id
                line_vals_list.append(vals)

        if line_vals_list:
            self.env['account.move.line'].with_context(
                check_move_validity=False,
            ).create(line_vals_list)

        if compensated_ids:
            new_move.with_context(check_move_validity=False).write({
                'compensated_invoice_ids': compensated_ids,
            })

        total_debit = sum(new_move.line_ids.mapped('debit'))
        total_credit = sum(new_move.line_ids.mapped('credit'))
        if abs(total_debit - total_credit) > 0.01:
            raise UserError(_(
                'El asiento generado está desbalanceado (Debe %.2f vs Haber %.2f). '
                'Revise el tipo de cambio y los montos.'
            ) % (total_debit, total_credit))

        self.move_id.message_post(body=_(
            'Se generó el asiento de compensación %s por %s %s.'
        ) % (
            new_move.name or _('(sin número)'),
            self.total_currency,
            self.currency_id.symbol or self.currency_id.name,
        ))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Asiento de Compensación'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': new_move.id,
            'target': 'current',
        }

    def _validate_before_confirm(self, selected):
        if not selected:
            raise UserError(_('Debe seleccionar al menos una factura a compensar.'))
        if self.currency_rate <= 0:
            raise UserError(_('El tipo de cambio debe ser mayor a cero.'))
        for line in selected:
            if line.amount_to_compensate <= 0:
                raise UserError(_(
                    'El monto a compensar de %s debe ser mayor a cero.'
                ) % line.invoice_id.name)
            if line.currency_id.compare_amounts(
                line.amount_to_compensate, line.amount_residual
            ) > 0:
                raise UserError(_(
                    'El monto a compensar de %s (%s) supera su saldo pendiente (%s).'
                ) % (
                    line.invoice_id.name,
                    line.amount_to_compensate,
                    line.amount_residual,
                ))
        total = sum(selected.mapped('amount_to_compensate'))
        if self.currency_id.compare_amounts(
            total, self.move_id.amount_residual
        ) > 0:
            raise UserError(_(
                'El total a compensar (%s) supera el saldo de la factura '
                'origen (%s).'
            ) % (total, self.move_id.amount_residual))
        if self.show_imbalance_treatment and not self.imbalance_treatment:
            if self.gap_exceeds_threshold:
                pass
            else:
                raise UserError(_(
                    'Debe seleccionar cómo tratar el desbalance antes de '
                    'generar el asiento.'
                ))
        if self.imbalance_treatment == 'exchange_diff' and not self.exchange_account_id:
            raise UserError(_(
                'Debe seleccionar la cuenta de ajuste.'
            ))
        if (self.imbalance_treatment == 'exchange_diff'
                and self.gap_exceeds_threshold):
            raise UserError(_(
                'El ajuste por diferencia de montos supera el máximo '
                'permitido. Solo se puede dejar como saldo pendiente.'
            ))

    # -------------------------------------------------------------------------
    # Construcción del asiento
    # -------------------------------------------------------------------------
    def _prepare_compensation_move(self, selected):
        """Arma el diccionario de creación del account.move.

        Reglas:
        - Cada CP se valoriza con el TC EXACTO de su propia factura (proporción
          contra su línea AR/AP), no con el TC del wizard. Esto evita AED
          automático al reconciliar.
        - El origen se valoriza con el TC EXACTO de su propia factura
          (origin_rate / origin_residual_local), no con el TC del wizard.
        - La línea de ajuste por diferencia de MONTOS va a la cuenta elegida
          por el usuario (exchange_account_id). Solo aparece cuando se eleva
          la CP a residual completo.
        - La línea de diferencia de TC va a la cuenta de compañía (77xx / 67xx).
          Su signo NO depende de si el origen es venta o compra: si el
          asiento requiere crédito para cuadrar → cuenta ganancia; si requiere
          débito → cuenta pérdida.
        """
        treatment = self.imbalance_treatment
        if not self.show_imbalance_treatment:
            treatment = 'leave_pending'

        is_sale = self.origin_type == 'sale'
        use_full_cp = (treatment == 'exchange_diff' and self.has_amount_gap)
        move_line_cmds = []

        # ---- Líneas por cada factura contraparte ----------------------------
        counterpart_local_total = 0.0
        origin_amount_cur = 0.0
        for line in selected:
            inv = line.invoice_id
            cp_account = self._get_ar_ap_account(inv)
            amount_cur = line.amount_residual if use_full_cp else line.amount_to_compensate
            origin_amount_cur += line.amount_to_compensate
            amount_local = self._get_line_local_amount(line, amount_cur)
            counterpart_local_total += amount_local

            if is_sale:
                # Origen venta → CP es compra → CxP al DEBE
                debit, credit = amount_local, 0.0
                amt_cur = amount_cur
            else:
                # Origen compra → CP es venta → CxC al HABER
                debit, credit = 0.0, amount_local
                amt_cur = -amount_cur

            move_line_cmds.append(Command.create({
                'account_id': cp_account.id,
                'partner_id': self.partner_id.id,
                'name': self._build_line_label(counterpart=inv),
                'debit': debit,
                'credit': credit,
                'amount_currency': amt_cur,
                'currency_id': self.currency_id.id,
            }))

        # ---- Línea agregada del origen (TC original del origen) -------------
        origin_account = self._get_ar_ap_account(self.move_id)
        origin_amount_local = self._get_origin_local_amount(origin_amount_cur)
        if is_sale:
            # Origen venta → CxC al HABER
            o_debit, o_credit = 0.0, origin_amount_local
            o_amt_cur = -origin_amount_cur
        else:
            # Origen compra → CxP al DEBE
            o_debit, o_credit = origin_amount_local, 0.0
            o_amt_cur = origin_amount_cur

        move_line_cmds.append(Command.create({
            'account_id': origin_account.id,
            'partner_id': self.partner_id.id,
            'name': self._build_line_label(counterpart=None, is_origin=True,
                                           counterparts=selected.mapped('invoice_id')),
            'debit': o_debit,
            'credit': o_credit,
            'amount_currency': o_amt_cur,
            'currency_id': self.currency_id.id,
        }))

        # ---- Línea de ajuste por diferencia de montos (cuenta del wizard) ---
        # Cuando elevamos las CPs a residual completo, el gap USD (× TC de la
        # CP) sale en soles a la cuenta elegida por el usuario.
        if use_full_cp:
            unelevated_local = sum(
                self._get_line_local_amount(line, line.amount_to_compensate)
                for line in selected
            )
            gap_local = counterpart_local_total - unelevated_local
            if not self.company_currency_id.is_zero(gap_local):
                # Origen compra: CxC haber aumentó por elevar CP → falta debe → ajuste al DEBE
                # Origen venta:  CxP debe aumentó por elevar CP → falta haber → ajuste al HABER
                if is_sale:
                    adj_debit, adj_credit = 0.0, gap_local
                else:
                    adj_debit, adj_credit = gap_local, 0.0
                move_line_cmds.append(Command.create({
                    'account_id': self.exchange_account_id.id,
                    'partner_id': self.partner_id.id,
                    'name': _('Ajuste por diferencia de montos en compensación'),
                    'debit': adj_debit,
                    'credit': adj_credit,
                    'amount_currency': 0.0,
                    'currency_id': self.currency_id.id,
                }))

        # ---- Línea de diferencia de tipo de cambio (cuenta de compañía) -----
        # REGLA CONTABLE UNIVERSAL (independiente de si origen es venta o compra):
        #   Balance > 0 (sobra debe)  → línea al HABER → GANANCIA → cuenta 77xx
        #   Balance < 0 (sobra haber) → línea al DEBE  → PÉRDIDA  → cuenta 67xx
        current_debit = 0.0
        current_credit = 0.0
        for cmd in move_line_cmds:
            if isinstance(cmd, (list, tuple)) and len(cmd) >= 3 and cmd[0] == 0:
                vals = cmd[2]
                current_debit += vals.get('debit', 0.0)
                current_credit += vals.get('credit', 0.0)
        current_balance = current_debit - current_credit

        if not self.company_currency_id.is_zero(current_balance):
            if current_balance > 0:
                # Sobra debe → cierra con crédito → es ganancia
                ed_debit, ed_credit = 0.0, current_balance
                account = self.company_id.compensation_exchange_gain_account_id
            else:
                # Sobra haber → cierra con débito → es pérdida
                ed_debit, ed_credit = -current_balance, 0.0
                account = self.company_id.compensation_exchange_loss_account_id

            move_line_cmds.append(Command.create({
                'account_id': account.id,
                'partner_id': self.partner_id.id,
                'name': _('Diferencia de tipo de cambio en compensación'),
                'debit': ed_debit,
                'credit': ed_credit,
                'amount_currency': 0.0,
                'currency_id': self.currency_id.id,
            }))

        compensated_ids = (selected.mapped('invoice_id') + self.move_id).ids

        return {
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': self._build_move_reference(selected),
            'is_compensation_move': True,
            'compensated_invoice_ids': [Command.set(compensated_ids)],
            'line_ids': move_line_cmds,
        }

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _get_ar_ap_account(self, move):
        line = move.line_ids.filtered(
            lambda l: l.account_id.account_type in (
                'asset_receivable', 'liability_payable'
            )
        )
        if not line:
            raise UserError(_(
                'La factura %s no tiene línea de cuenta por cobrar/pagar.'
            ) % move.name)
        return line[0].account_id

    def _build_move_reference(self, selected):
        cp_names = ' Y '.join(selected.mapped('invoice_id.name'))
        return _('APLIC.COMPENSACION %s %s - CON %s') % (
            self.move_id.name,
            self.partner_id.name,
            cp_names,
        )

    def _build_line_label(self, counterpart=None, is_origin=False, counterparts=None):
        if is_origin:
            cp_names = ' Y '.join(c.name for c in (counterparts or []))
            return _('APLIC.COMPENSACION %s %s - CON %s') % (
                self.move_id.name, self.partner_id.name, cp_names,
            )
        return _('APLIC.COMPENSACION %s %s - CON %s') % (
            self.move_id.name, self.partner_id.name, counterpart.name,
        )