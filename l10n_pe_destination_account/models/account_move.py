from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    destination_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento de Destino",
        copy=False,
        readonly=True,
        ondelete="cascade",
        help="Asiento de destino automático generado por este movimiento.",
    )

    def _l10n_pe_skip_destination_by_journal(self):
        self.ensure_one()
        return bool(self.journal_id and self.journal_id.no_generate_destinations)

    # # -------------------------------------------------------------------------
    # # LÓGICA DE CREACIÓN DE ASIENTOS
    # # -------------------------------------------------------------------------
    # def _l10n_pe_create_account_destination_lines(self, line):
    #     """
    #     Crea los 'vals' para las líneas de destino basadas en 'account.account'.
    #     B.P.: Lógica de redondeo "plug" (total - acumulado) implementada.
    #     """
    #     destination_lines_vals = []
    #     destination_accounts = line.account_id.destination_account_ids

    #     # Totales a distribuir
    #     total_debit = line.debit
    #     total_credit = line.credit
    #     total_amount_currency = line.amount_currency

    #     # Acumuladores para el redondeo
    #     running_debit = 0.0
    #     running_credit = 0.0
    #     running_amount_currency = 0.0

    #     for i, acc_line in enumerate(destination_accounts):
    #         is_last_line = i == len(destination_accounts) - 1

    #         if is_last_line:
    #             # B.P.: Última línea (plug)
    #             debit = total_debit - running_debit
    #             credit = total_credit - running_credit
    #             amount_currency = total_amount_currency - running_amount_currency
    #         else:
    #             # B.P.: Líneas intermedias (cálculo por %)
    #             percentage = acc_line.percentage
    #             debit, credit, amount_currency = (
    #                 self._l10n_pe_calculate_destination_amounts(line, percentage)
    #             )
    #             running_debit += debit
    #             running_credit += credit
    #             running_amount_currency += amount_currency

    #         destination_lines_vals.append(
    #             self._l10n_pe_prepare_destination_line(
    #                 line,
    #                 acc_line.destination_account_id.id,
    #                 amount_currency,
    #                 debit,
    #                 credit,
    #             )
    #         )

    #     # Línea de contrapartida (balance)
    #     destination_lines_vals.append(
    #         self._l10n_pe_prepare_destination_line(
    #             line,
    #             line.account_id.destination_account_counterpart_id.id,
    #             -total_amount_currency,  # Invertir moneda
    #             total_credit,  # Invertir deb/cred
    #             total_debit,  # Invertir deb/cred
    #         )
    #     )
    #     return destination_lines_vals

    # def _l10n_pe_create_analytic_destination_lines(self, line):
    #     """
    #     Crea los 'vals' para las líneas de destino basadas en 'account.analytic.account'.
    #     B.P.: Lógica de redondeo "plug" y pre-carga de analíticas.
    #     """
    #     destination_lines_vals = []

    #     # B.P.: Pre-cargar todas las analíticas
    #     analytic_ids_to_check = set()
    #     for key in line.analytic_distribution.keys():
    #         analytic_ids_to_check.update(map(int, key.split(",")))

    #     analytic_accounts = (
    #         self.env["account.analytic.account"]
    #         .browse(list(analytic_ids_to_check))
    #         .filtered("has_destination_account")
    #     )
    #     analytic_accounts_map = {acc.id: acc for acc in analytic_accounts}

    #     # Filtrar solo las distribuciones que tienen config de destino
    #     relevant_distributions = []
    #     for key, percentage in line.analytic_distribution.items():
    #         for acc_id in map(int, key.split(",")):
    #             if acc_id in analytic_accounts_map:
    #                 relevant_distributions.append(
    #                     (analytic_accounts_map[acc_id], float(percentage))
    #                 )

    #     if not relevant_distributions:
    #         return []

    #     # Totales a distribuir
    #     total_debit = line.debit
    #     total_credit = line.credit
    #     total_amount_currency = line.amount_currency

    #     # Acumuladores
    #     running_debit = 0.0
    #     running_credit = 0.0
    #     running_amount_currency = 0.0

    #     for i, (analytic_account, percentage) in enumerate(relevant_distributions):
    #         is_last_line = i == len(relevant_distributions) - 1

    #         if is_last_line:
    #             debit = total_debit - running_debit
    #             credit = total_credit - running_credit
    #             amount_currency = total_amount_currency - running_amount_currency
    #         else:
    #             debit, credit, amount_currency = (
    #                 self._l10n_pe_calculate_destination_amounts(line, percentage)
    #             )
    #             running_debit += debit
    #             running_credit += credit
    #             running_amount_currency += amount_currency

    #         # Línea de Destino
    #         destination_lines_vals.append(
    #             self._l10n_pe_prepare_destination_line(
    #                 line,
    #                 analytic_account.destination_account_id.id,
    #                 amount_currency,
    #                 debit,
    #                 credit,
    #             )
    #         )
    #         # Línea de Contrapartida
    #         destination_lines_vals.append(
    #             self._l10n_pe_prepare_destination_line(
    #                 line,
    #                 analytic_account.destination_account_counterpart_id.id,
    #                 -amount_currency,
    #                 credit,
    #                 debit,
    #             )
    #         )

    #     return destination_lines_vals

    # # -------------------------------------------------------------------------
    # # MÉTODOS HELPER (Cálculo y Preparación)
    # # -------------------------------------------------------------------------
    # def _l10n_pe_calculate_destination_amounts(self, line, percentage):
    #     """
    #     Calcula los montos para una línea de destino basado en un porcentaje.
    #     B.P.: Usar 'line.company_id.currency_id.round' es más seguro que 'line.currency_id'.
    #     El 'currency_id' en la línea puede ser extranjero, pero el 'debit'/'credit'
    #     siempre están en la moneda de la compañía.
    #     """
    #     currency = line.company_id.currency_id

    #     amount_currency = 0.0
    #     # Solo calcular 'amount_currency' si la línea tiene una moneda (distinta a la compañía)
    #     if line.currency_id and line.currency_id != currency:
    #         amount_currency = line.currency_id.round(
    #             (line.amount_currency * percentage) / 100
    #         )

    #     debit = currency.round((line.debit * percentage) / 100)
    #     credit = currency.round((line.credit * percentage) / 100)

    #     return debit, credit, amount_currency

    # def _l10n_pe_prepare_destination_line(
    #     self, line, account_id, amount_currency, debit, credit
    # ):
    #     """
    #     Prepara el diccionario de 'vals' (comando 0,0,vals) para un nuevo apunte.
    #     """
    #     return (
    #         0,
    #         0,
    #         {
    #             "name": line.name,
    #             "account_id": account_id,
    #             "date": line.date,
    #             "amount_currency": amount_currency,
    #             "currency_id": line.currency_id.id,
    #             "debit": debit,
    #             "credit": credit,
    #             "serie_correlative": line.serie_correlative,
    #             "l10n_latam_document_type_id": line.l10n_latam_document_type_id.id,
    #             "partner_id": line.partner_id.id,
    #         },
    #     )

    # ---------------------------------------------------------------------------- #
    #                           TODO - EXTENSIÓN DE VISTA                          #
    # ---------------------------------------------------------------------------- #
    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        """
        Modificación de vista para ocultar campos según el país.
        """
        arch, view = super()._get_view(view_id, view_type, **options)

        if hasattr(self, "_tags_invisible_per_country"):
            pe_country = self.env.ref("base.pe", raise_if_not_found=False)

            if pe_country:
                tags = [
                    ("field", "destination_move_id"),
                    ("button", "l10n_pe_open_destination_move"),
                ]

                arch, view = self._tags_invisible_per_country(
                    arch=arch,
                    view=view,
                    view_type=view_type,
                    tags=tags,
                    countries=[pe_country],
                )
        return arch, view

    # ---------------------------------------------------------------------------- #
    #            TODO - LIFECYCLE METHODS (POST, CANCEL, DRAFT, UNLINK)            #
    # ---------------------------------------------------------------------------- #
    def _post(self, soft=True):
        res = super()._post(soft=soft)

        if self.env.context.get("skip_destination_move_generation"):
            return res

        pe_moves = self.filtered(lambda m: m.company_id.country_id.code == "PE")
        if not pe_moves:
            return res

        pe_moves = pe_moves.filtered(lambda m: not m.journal_id.no_generate_destinations)
        if not pe_moves:
            return res

        moves_to_process = pe_moves.filtered(lambda m: m._l10n_pe_has_destination_accounts())

        ctx = dict(self.env.context, skip_destination_move_generation=True)
        for move in moves_to_process:
            move.with_context(ctx)._l10n_pe_validate_destination_move()
            move.with_context(ctx)._l10n_pe_post_destination_move()

        return res

    def write(self, vals):
        """
        Sobrescribimos write para detectar cambios en las líneas de asientos YA publicados.
        Esto es crucial para la Conciliación Bancaria, que modifica asientos publicados.
        """
        # 1. Ejecutar la escritura estándar primero
        res = super().write(vals)

        # 2. Verificar si se han tocado las líneas contables ('line_ids')
        # Detectar cambios en líneas de asientos YA publicados (Conciliación Bancaria)
        if "line_ids" in vals and not self.env.context.get(
            "skip_destination_move_generation"
        ):
            # Filtramos asientos que:
            # a) Sean de Perú
            # b) Estén PUBLICADOS (si fueran borrador, el _post lo agarrará luego)
            # c) Tengan configuración de destino
            moves_to_update = self.filtered(
                lambda m: m.state == "posted"
                and m.company_id.country_id.code == "PE"
                and not m.journal_id.no_generate_destinations
                and m._l10n_pe_has_destination_accounts()
            )

            ctx = dict(self.env.context, skip_destination_move_generation=True)
            for move in moves_to_update:
                # la actualización (write) si existe un destination_move_id,
                # esto es seguro y no duplicará asientos.
                try:
                    move.with_context(ctx)._l10n_pe_validate_destination_move()
                    move.with_context(ctx)._l10n_pe_post_destination_move()
                except Exception as e:
                    # En conciliación bancaria es peligroso lanzar errores bloqueantes
                    # porque puede romper la UI del widget.
                    # Lo mejor es loguear el error o dejar pasar si es crítico.
                    # Por ahora, dejamos que falle si la validación no pasa.
                    raise e

        return res

    def button_cancel(self):
        """
        Cancela los asientos de destino en lote.
        """
        dest_moves = self.mapped("destination_move_id")
        moves_to_cancel = dest_moves.filtered(lambda m: m.state == "draft")
        if moves_to_cancel:
            moves_to_cancel.button_cancel()

        return super().button_cancel()

    def button_draft(self):
        """
        Revierte a borrador los asientos de destino en lote.
        """
        dest_moves = self.mapped("destination_move_id")
        moves_to_draft = dest_moves.filtered(lambda m: m.state in ["posted", "cancel"])
        if moves_to_draft:
            moves_to_draft.button_draft()

        return super().button_draft()

    # ---------------------------------------------------------------------------- #
    #                          TODO - ACCIONES DE BOTONES                          #
    # ---------------------------------------------------------------------------- #
    def l10n_pe_open_destination_move(self):
        """
        Abre la vista formulario del asiento de destino vinculado.
        """
        self.ensure_one()
        view_id = self.env["account.move"].get_formview_id()

        return {
            "type": "ir.actions.act_window",
            "name": _("Asiento de Destino"),
            "res_model": "account.move",
            "view_mode": "form",
            "views": [(view_id, "form")],
            "view_id": view_id,
            "res_id": self.destination_move_id.id,
            "target": "current",
        }

    # ---------------------------------------------------------------------------- #
    #                          TODO - LÓGICA DE VALIDACIÓN                         #
    # ---------------------------------------------------------------------------- #
    # def _l10n_pe_validate_account_destination(self, account):
    #     """
    #     Valida que una CUENTA CONTABLE tenga la config. necesaria.
    #     """
    #     if not account.destination_account_counterpart_id:
    #         raise ValidationError(
    #             _(
    #                 "La cuenta contable '%(name)s' no tiene una 'Cuenta de contrapartida' "
    #                 "configurada para el asiento de destino."
    #             )
    #             % {"name": account.name}
    #         )

    def _l10n_pe_validate_analytic_destination(self, analytic_account):
        """
        Valida que una CUENTA ANALÍTICA tenga la config. necesaria.
        """
        if not analytic_account.destination_account_id:
            raise ValidationError(
                _(
                    "La cuenta analítica '%(name)s' no tiene una 'Cuenta de destino' "
                    "configurada para el asiento de destino."
                )
                % {"name": analytic_account.name}
            )
        if not analytic_account.destination_account_counterpart_id:
            raise ValidationError(
                _(
                    "La cuenta analítica '%(name)s' no tiene una 'Cuenta de contrapartida' "
                    "configurada para el asiento de destino."
                )
                % {"name": analytic_account.name}
            )

    def _l10n_pe_validate_destination_move(self):
        """
        Validación principal: comprueba diario y todas las líneas.
        """
        self.ensure_one()

        if self._l10n_pe_skip_destination_by_journal():
            return

        if not self.company_id.destination_account_journal_id:
            raise ValidationError(
                _(
                    "El 'Diario para Distribución' no está configurado para "
                    "la compañía %(name)s. Por favor, configúrelo en los Ajustes de Contabilidad."
                )
                % {"name": self.company_id.name}
            )

        # Pre-cargar todas las cuentas analíticas relevantes
        analytic_ids_to_check = set()
        for line in self.line_ids:
            if line.analytic_distribution:
                for key in line.analytic_distribution.keys():
                    analytic_ids_to_check.update(map(int, key.split(",")))

        # Un solo 'browse' para todas las cuentas
        analytic_accounts = (
            self.env["account.analytic.account"]
            .browse(list(analytic_ids_to_check))
            .filtered("has_destination_account")
        )
        analytic_accounts_map = {acc.id: acc for acc in analytic_accounts}

        accounts_to_check = set()

        for line in self.line_ids:
            # 1. Validar Cuenta Contable
            if line.account_id.has_destination_account:
                accounts_to_check.add(line.account_id)

                # 2. Validar Cuentas Analíticas
                if line.analytic_distribution:
                    for key in line.analytic_distribution.keys():
                        for acc_id in map(int, key.split(",")):
                            if acc_id in analytic_accounts_map:
                                self._l10n_pe_validate_analytic_destination(
                                    analytic_accounts_map[acc_id]
                                )

        # # 3. Validar cuentas contables (una sola vez por cuenta)
        # for account in accounts_to_check:
        #     self._l10n_pe_validate_account_destination(account)

    # ---------------------------------------------------------------------------- #
    #                     TODO - LÓGICA DE CREACIÓN DE ASIENTOS                    #
    # ---------------------------------------------------------------------------- #
    def _l10n_pe_post_destination_move(self):
        """
        Wrapper para crear o actualizar el asiento de destino.
        """
        self.ensure_one()

        if self._l10n_pe_skip_destination_by_journal():
            return

        journal = self.company_id.destination_account_journal_id

        lines_with_config = self.line_ids.filtered(
            lambda line: line.account_id.has_destination_account
            and self._l10n_pe_line_has_analytic_destination(line)
        )

        if lines_with_config:
            self._l10n_pe_create_destination_move(lines_with_config, journal)

    def _l10n_pe_create_destination_move(self, lines, journal):
        """
        Crea/actualiza el asiento de destino y sus apuntes.
        """
        self.ensure_one()
        destination_lines_vals = []

        for line in lines:
            # if line.account_id.has_destination_account:
            #     destination_lines_vals.extend(
            #         self._l10n_pe_create_account_destination_lines(line)
            #     )

            if self._l10n_pe_line_has_analytic_destination(line):
                destination_lines_vals.extend(
                    self._l10n_pe_create_analytic_destination_lines(line)
                )

        destination_move_vals = {
            "partner_id": self.partner_id.id,
            "journal_id": journal.id,
            "company_id": self.company_id.id,
            "date": self.date,
            "move_type": "entry",
            "state": "draft",
            "ref": _("Asiento de Destino: %s") % self.name,
            "line_ids": [(5, 0, 0)] + destination_lines_vals,
        }

        if self.destination_move_id:
            if self.destination_move_id.state in ["posted", "cancel"]:
                self.destination_move_id.button_draft()
            self.destination_move_id.write(destination_move_vals)
            self.destination_move_id._post()
        else:
            destination_move = self.env["account.move"].create(destination_move_vals)
            destination_move._post()
            self.write({"destination_move_id": destination_move.id})

    # def _l10n_pe_create_account_destination_lines(self, line):
    #     destination_lines = []
    #     destination_accounts = line.account_id.destination_account_ids
    #     total_amount_currency = total_debit = total_credit = 0

    #     for idx, account in enumerate(destination_accounts):
    #         amount_currency, debit, credit = (
    #             self._l10n_pe_calculate_destination_amounts(line, account.percentage)
    #         )
    #         total_amount_currency += amount_currency
    #         total_debit += debit
    #         total_credit += credit

    #         if idx == len(destination_accounts) - 1:
    #             amount_currency, debit, credit = (
    #                 self._l10n_pe_adjust_final_destination_move(
    #                     line,
    #                     total_amount_currency,
    #                     total_debit,
    #                     total_credit,
    #                     amount_currency,
    #                     debit,
    #                     credit,
    #                 )
    #             )

    #         destination_lines.append(
    #             self._l10n_pe_prepare_destination_line(
    #                 line,
    #                 account.destination_account_id.id,
    #                 amount_currency,
    #                 debit,
    #                 credit,
    #             )
    #         )

    #     destination_lines.append(
    #         self._l10n_pe_prepare_destination_line(
    #             line,
    #             line.account_id.destination_account_counterpart_id.id,
    #             -line.amount_currency,
    #             line.credit,
    #             line.debit,
    #         )
    #     )

    #     return destination_lines

    def _l10n_pe_create_analytic_destination_lines(self, line):
        destination_lines = []
        total_amount_currency = total_debit = total_credit = 0

        analytic_account_ids = []
        for key in line.analytic_distribution.keys():
            analytic_account_ids.extend(map(int, key.split(",")))

        analytic_accounts = self.env["account.analytic.account"].browse(
            analytic_account_ids
        )

        for idx, (analytic_account_id, percentage) in enumerate(
            line.analytic_distribution.items()
        ):
            for single_analytic_account_id in analytic_account_id.split(","):
                analytic_account = analytic_accounts.filtered(
                    lambda a: a.id == int(single_analytic_account_id)
                )
                if analytic_account.has_destination_account:
                    amount_currency, debit, credit = (
                        self._l10n_pe_calculate_destination_amounts(
                            line, float(percentage)
                        )
                    )
                    total_amount_currency += amount_currency
                    total_debit += debit
                    total_credit += credit

                    if idx == len(line.analytic_distribution) - 1:
                        amount_currency, debit, credit = (
                            self._l10n_pe_adjust_final_destination_move(
                                line,
                                total_amount_currency,
                                total_debit,
                                total_credit,
                                amount_currency,
                                debit,
                                credit,
                            )
                        )

                    destination_lines.append(
                        self._l10n_pe_prepare_destination_line(
                            line,
                            analytic_account.destination_account_id.id,
                            amount_currency,
                            debit,
                            credit,
                        )
                    )

                    destination_lines.append(
                        self._l10n_pe_prepare_destination_line(
                            line,
                            analytic_account.destination_account_counterpart_id.id,
                            -amount_currency,
                            credit,
                            debit,
                        )
                    )

        return destination_lines

    # ---------------------------------------------------------------------------- #
    #                 TODO - METODOS HELPER (Cálculo y Preparación)                #
    # ---------------------------------------------------------------------------- #
    def _l10n_pe_line_has_analytic_destination(self, line):
        """
        Comprueba si alguna cuenta analítica en la línea
        tiene configuración de destino.
        """
        if not line.analytic_distribution:
            return False

        analytic_ids_to_check = set()
        for key in line.analytic_distribution.keys():
            analytic_ids_to_check.update(map(int, key.split(",")))

        if not analytic_ids_to_check:
            return False

        return (
            self.env["account.analytic.account"].search_count(
                [
                    ("id", "in", list(analytic_ids_to_check)),
                    ("has_destination_account", "=", True),
                ]
            )
            > 0
        )

    def _l10n_pe_has_destination_accounts(self):
        """
        Comprueba si el asiento (self) tiene *alguna* línea
        que requiera un asiento de destino.
        """
        self.ensure_one()
        
        if self._l10n_pe_skip_destination_by_journal():
            return False
        
        return any(
            line.account_id.has_destination_account
            and self._l10n_pe_line_has_analytic_destination(line)
            for line in self.line_ids
        )

    @staticmethod
    def _l10n_pe_adjust_final_destination_move(
        line,
        total_amount_currency,
        total_debit,
        total_credit,
        amount_currency,
        debit,
        credit,
    ):
        adjustment_amount_currency = (
            total_amount_currency - line.amount_currency
            if line.amount_currency != total_amount_currency
            else 0
        )
        adjustment_debit = total_debit - line.debit if line.debit != total_debit else 0
        adjustment_credit = (
            total_credit - line.credit if line.credit != total_credit else 0
        )
        return (
            line.currency_id.round(amount_currency - adjustment_amount_currency),
            line.currency_id.round(debit - adjustment_debit),
            line.currency_id.round(credit - adjustment_credit),
        )

    @staticmethod
    def _l10n_pe_calculate_destination_amounts(line, percentage):
        amount_currency = line.currency_id.round(
            (line.amount_currency * percentage) / 100
        )
        debit = line.currency_id.round((line.debit * percentage) / 100)
        credit = line.currency_id.round((line.credit * percentage) / 100)
        return amount_currency, debit, credit

    @staticmethod
    def _l10n_pe_prepare_destination_line(
        line, account_id, amount_currency, debit, credit
    ):
        return (
            0,
            0,
            {
                "name": line.name,
                "account_id": account_id,
                "date": line.date,
                "amount_currency": amount_currency,
                "currency_id": line.currency_id.id,
                "debit": debit,
                "credit": credit,
                "analytic_distribution": line.analytic_distribution,  # ← NUEVO
                "serie_correlative": line.serie_correlative,
                "l10n_latam_document_type_id": (
                    line.l10n_latam_document_type_id.id
                    if line.l10n_latam_document_type_id
                    else False
                ),
                "partner_id": line.partner_id.id if line.partner_id else False,
            },
        )

    # ---------------------------------------------------------------------------- #
    #                     TODO - ACCIÓN MASIVA (Server Action)                     #
    # ---------------------------------------------------------------------------- #
    def action_create_destination_move(self):
        """
        Acción de servidor para crear asientos de destino masivamente.
        """
        created_count = 0
        skipped_count = 0
        error_list = []

        # Filtrar por país primero
        pe_moves = self.filtered(lambda m: m.company_id.country_id.code == "PE")

        for move in pe_moves:
            try:
                if move.journal_id.no_generate_destinations:
                    skipped_count += 1
                    continue

                if move.destination_move_id:
                    skipped_count += 1
                    continue

                if not move._l10n_pe_has_destination_accounts():
                    skipped_count += 1
                    continue

                move._l10n_pe_validate_destination_move()
                move._l10n_pe_post_destination_move()
                created_count += 1

            except (ValidationError, UserError) as e:
                # Capturar errores de validación esperados
                error_list.append(
                    _("Error en %(move)s: %(error)s")
                    % {"move": move.name, "error": e.name}
                )
                move.message_post(
                    body=_("Error al crear asiento de destino: %s") % e.name
                )
            except Exception as e:
                # Capturar errores inesperados
                error_list.append(
                    _("Error inesperado en %(move)s: %(error)s")
                    % {"move": move.name, "error": str(e)}
                )
                move.message_post(
                    body=_("Error inesperado al crear asiento de destino: %s") % str(e)
                )

        # Preparar el mensaje de notificación final
        message_lines = [
            _("Proceso completado:"),
            _("- Asientos de destino creados/actualizados: %s") % created_count,
            _("- Asientos omitidos (ya existían o no aplicaban): %s") % skipped_count,
            _("- Errores encontrados: %s") % len(error_list),
        ]
        if error_list:
            message_lines.append(_("Detalle de errores:"))
            message_lines.extend(error_list)

        notification_type = "success" if not error_list else "warning"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Creación de Asientos de Destino"),
                "message": "\n".join(message_lines),
                "sticky": True,
                "type": notification_type,
            },
        }
