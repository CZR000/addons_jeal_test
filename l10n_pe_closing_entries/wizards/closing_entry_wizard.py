# -*- coding: utf-8 -*-
"""Asistente de generación de asientos de cierre contable (PCGE - Perú).

Diseño general
--------------
1. Se leen los saldos del periodo UNA sola vez, agregados por la BD
   (`_read_group`), en "buckets" (cuenta + moneda + detalle opcional).
2. La cadena de cierre se resuelve por NIVELES topológicos descendentes:
   `closing_depth` indica cuántos saltos faltan hasta el final de la cadena,
   de modo que 60 (nivel 2) se cierra contra 89 antes de que 89 (nivel 1) se
   cierre contra 59. Cada nivel produce sus propios asientos: nunca se mezclan.
3. El saldo transferido a la cuenta destino se acumula en memoria, por lo que
   el nivel siguiente ve el saldo real aunque los asientos queden en borrador.
4. La generación es IDEMPOTENTE: los asientos de cierre ya creados por el
   módulo (incluidos los borradores) se consideran al calcular el saldo, así
   que una segunda corrida sólo procesa lo que realmente queda pendiente.
"""
import ast
import json
from collections import defaultdict
from typing import NamedTuple

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression

# Clases del PCGE peruano.
BALANCE_CLASSES = tuple("012345")
RESULT_CLASSES = tuple("6789")

ACCOUNT_CLASS_LABELS = {
    "balance": "Cuentas de Balance",
    "result": "Cuentas de Resultado",
    "other": "Otras Cuentas",
}

# Políticas de `account_analytic_required` que exigen distribución analítica.
ANALYTIC_REQUIRED_POLICIES = ("always", "posted")


class ClosingBucket(NamedTuple):
    """Clave de agregación de un saldo a cerrar.

    Se usa una tupla nombrada (hashable e inmutable) en lugar de un dict para
    poder indexar los saldos y mantener el código legible.
    """

    account_id: int
    currency_id: int = 0
    product_id: int = 0
    partner_id: int = 0
    analytic_key: str = ""


class ClosingEntryWizard(models.TransientModel):
    _name = "closing.entry.wizard"
    _description = "Asistente de Asientos de Cierre Contable"

    # Mapeo entre la configuración de detalle y el campo de account.move.line.
    _DETAIL_FIELDS = {"product": "product_id", "partner": "partner_id"}

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    date_from = fields.Date(
        string="Fecha de Inicio",
        required=True,
        help="Fecha inicial del periodo cuyos saldos se van a cerrar.",
    )

    date_to = fields.Date(
        string="Fecha de Fin",
        required=True,
        help="Fecha final del periodo cuyos saldos se van a cerrar.",
    )

    closing_date = fields.Date(
        string="Fecha del Asiento",
        required=True,
        default=fields.Date.context_today,
        help="Fecha contable con la que se registran los asientos generados.",
    )

    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario",
        required=True,
        check_company=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        default=lambda self: self._default_journal_id(),
    )

    line_label = fields.Char(
        string="Glosa",
        required=True,
        default="Asiento de cierre de ejercicio",
        help="Texto que se usará como etiqueta de las líneas del asiento.",
    )

    entry_grouping = fields.Selection(
        selection=[
            ("level", "Un asiento por nivel"),
            ("class", "Por nivel y clase de cuenta"),
            ("class_sign", "Por nivel, clase de cuenta y signo del saldo"),
        ],
        string="Agrupación de Asientos",
        required=True,
        default="class_sign",
        help="Determina en cuántos asientos se reparte cada nivel de la cadena "
             "de cierre. En todos los casos, niveles distintos siempre generan "
             "asientos distintos.",
    )

    analytic_mode = fields.Selection(
        selection=[
            ("replicate", "Replicar la distribución analítica del origen"),
            ("ignore", "Sin distribución analítica"),
        ],
        string="Analítica",
        required=True,
        default="replicate",
        help="'Replicar' desglosa el saldo de las cuentas con política analítica "
             "obligatoria por distribución, evitando tener que saltarse la "
             "validación. 'Sin distribución' mantiene el comportamiento anterior "
             "y pedirá confirmación.",
    )

    replace_drafts = fields.Boolean(
        string="Reemplazar Borradores Existentes",
        help="Elimina los asientos de cierre en borrador del mismo periodo antes "
             "de generar. Los asientos publicados nunca se eliminan.",
    )

    auto_post = fields.Boolean(
        string="Publicar Asientos",
        help="Publica automáticamente los asientos generados. Si se desmarca, "
             "quedan en borrador para su revisión.",
    )

    existing_move_ids = fields.Many2many(
        comodel_name="account.move",
        string="Asientos de Cierre del Periodo",
        compute="_compute_existing_move_ids",
    )

    existing_move_count = fields.Integer(
        string="N.º de Asientos Existentes",
        compute="_compute_existing_move_ids",
    )

    # ------------------------------------------------------------------
    # Defaults / computes / constraints
    # ------------------------------------------------------------------
    @api.model
    def _default_journal_id(self):
        return self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )

    @api.depends("company_id", "date_from", "date_to")
    def _compute_existing_move_ids(self):
        Move = self.env["account.move"]
        for wizard in self:
            moves = Move.browse()
            if wizard.company_id and wizard.date_from and wizard.date_to:
                moves = Move.search(
                    Move._get_closing_entry_domain(
                        wizard.company_id, wizard.date_from, wizard.date_to
                    )
                )
            wizard.existing_move_ids = moves
            wizard.existing_move_count = len(moves)

    @api.constrains("date_from", "date_to", "closing_date")
    def _check_dates(self):
        for wizard in self:
            if not (wizard.date_from and wizard.date_to and wizard.closing_date):
                continue
            if wizard.date_from > wizard.date_to:
                raise ValidationError(
                    _("La fecha de inicio no puede ser posterior a la fecha de fin.")
                )
            if wizard.closing_date < wizard.date_to:
                raise ValidationError(
                    _(
                        "La fecha del asiento (%(closing)s) no puede ser anterior "
                        "al fin del periodo a cerrar (%(date_to)s).",
                        closing=wizard.closing_date,
                        date_to=wizard.date_to,
                    )
                )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.journal_id.company_id != self.company_id:
            self.journal_id = self.with_company(self.company_id)._default_journal_id()

    # ------------------------------------------------------------------
    # Acciones públicas
    # ------------------------------------------------------------------
    def action_view_existing_moves(self):
        """Abre los asientos de cierre ya existentes para el periodo."""
        self.ensure_one()
        action = self._get_moves_action()
        action["domain"] = [("id", "in", self.existing_move_ids.ids)]
        return action

    def _get_moves_action(self):
        """Acción base de asientos contables, en modo sólo consulta.

        Se conserva el contexto original de la acción (`default_move_type`,
        `view_no_maturity`, ...) pero se retiran los filtros por defecto:
        `account.action_move_journal_line` trae `search_default_posted=1`, que
        ocultaría precisamente los asientos de cierre en borrador que se acaban
        de generar. El dominio por ids ya acota el resultado.
        """
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account.action_move_journal_line"
        )
        try:
            context = ast.literal_eval(action.get("context") or "{}")
        except (ValueError, SyntaxError):
            context = {}
        context = {
            key: value
            for key, value in context.items()
            if not key.startswith("search_default_")
        }
        context["create"] = False
        action["context"] = context
        return action

    def action_generate_entries(self):
        """Genera los asientos de cierre del periodo.

        Flujo:
        1. Calcula los saldos pendientes y prepara los asientos por nivel.
        2. Si quedan cuentas con analítica obligatoria sin distribución, pide
           confirmación explícita y NO modifica nada.
        3. Sólo tras superar ese punto se eliminan los borradores previos (si
           se pidió reemplazarlos) y se crean los asientos en una única llamada
           a `create`, publicándolos en lote si corresponde.

        El orden es deliberado: si el usuario cancela el diálogo de
        confirmación, no debe haberse borrado ningún asiento.
        """
        self.ensure_one()
        # `code` es dependiente de compañía en Odoo 18: fijamos la compañía.
        wizard = self.with_company(self.company_id)
        forced = bool(self.env.context.get("closing_entry_force_create"))

        existing_moves = wizard._get_existing_closing_moves()
        move_vals_list = wizard._prepare_closing_moves()
        if not move_vals_list:
            raise UserError(wizard._get_nothing_to_close_message(existing_moves))

        if not forced:
            missing_accounts = wizard._get_accounts_missing_analytic(move_vals_list)
            if missing_accounts:
                return wizard._action_confirm_missing_analytic(missing_accounts)

        # --- Punto de no retorno: a partir de aquí se escribe en la BD. ---
        if wizard.replace_drafts:
            existing_moves.filtered(lambda move: move.state == "draft").unlink()

        Move = self.env["account.move"]
        if forced:
            Move = Move.with_context(skip_analytic_policy_check=True)

        moves = Move.create(move_vals_list)
        if wizard.auto_post:
            moves.action_post()
        return wizard._action_open_moves(moves)

    # ------------------------------------------------------------------
    # Selección de cuentas y saldos
    # ------------------------------------------------------------------
    def _get_accounts_to_close(self):
        """Cuentas de la compañía con una cuenta de cierre configurada.

        Se validan aquí (y no sólo por constraint) dos condiciones que sólo
        pueden comprobarse en el contexto de la compañía que se está cerrando:
        que la cuenta destino esté disponible en esa compañía y que las monedas
        forzadas de origen y destino sean compatibles. Se prefiere fallar con un
        mensaje claro antes que omitir cuentas en silencio.
        """
        Account = self.env["account.account"]
        domain = Account._check_company_domain(self.company_id) + [
            ("closing_account_id", "!=", False),
            ("deprecated", "=", False),
            ("account_type", "!=", "off_balance"),
        ]
        accounts = Account.search(domain, order="closing_depth desc, code")
        self._check_closing_targets(accounts)
        return accounts

    def _check_closing_targets(self, accounts):
        """Valida las cuentas destino antes de construir ningún asiento."""
        wrong_company = accounts.filtered(
            lambda account: self.company_id not in account.closing_account_id.company_ids
        )
        if wrong_company:
            raise UserError(
                _(
                    "Las siguientes cuentas tienen una cuenta de cierre que no "
                    "pertenece a la compañía %(company)s:\n\n- %(accounts)s",
                    company=self.company_id.display_name,
                    accounts="\n- ".join(wrong_company.mapped("display_name")),
                )
            )

        wrong_currency = accounts.filtered(
            lambda account: account.closing_account_id.currency_id
            and account.closing_account_id.currency_id != account.currency_id
            and account.currency_id
        )
        if wrong_currency:
            raise UserError(
                _(
                    "Las siguientes cuentas y sus cuentas de cierre tienen monedas "
                    "forzadas distintas, lo que impediría cuadrar el asiento:\n\n- %s",
                    "\n- ".join(wrong_currency.mapped("display_name")),
                )
            )

    def _get_current_closing_move_domain(self):
        """Identifica los asientos de cierre ya generados para ESTE periodo."""
        return [
            ("move_id.is_closing_entry", "=", True),
            ("move_id.closing_date_from", "=", self.date_from),
            ("move_id.closing_date_to", "=", self.date_to),
        ]

    def _get_move_line_domain(self, accounts):
        """Dominio de apuntes considerados para el cálculo de saldos.

        Se suman dos conjuntos disjuntos:

        * Movimientos ordinarios publicados dentro del periodo. Se excluye
          cualquier asiento de cierre: los de otros ejercicios sólo revierten
          saldos que ya no pertenecen a este periodo (aunque su fecha contable
          caiga dentro), y los de este periodo entran por el segundo término.
        * Apuntes de los asientos de cierre de ESTE periodo, en borrador o
          publicados, **con independencia de su fecha contable** (la fecha del
          asiento de cierre puede ser posterior a `date_to`).

        Este segundo término es lo que hace idempotente la generación: si ya se
        corrió el cierre, esas cuentas ya no presentan saldo pendiente y no se
        vuelven a cerrar. Cuando se pide reemplazar los borradores, éstos se
        ignoran porque van a eliminarse.
        """
        own_states = ("posted",) if self.replace_drafts else ("draft", "posted")
        period_lines = [
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("move_id.state", "=", "posted"),
            ("move_id.is_closing_entry", "=", False),
        ]
        own_closing_lines = expression.AND(
            [
                self._get_current_closing_move_domain(),
                [("move_id.state", "in", own_states)],
            ]
        )
        return expression.AND(
            [
                [
                    ("account_id", "in", accounts.ids),
                    ("company_id", "=", self.company_id.id),
                ],
                expression.OR([period_lines, own_closing_lines]),
            ]
        )

    def _requires_analytic(self, account):
        """¿La política analítica de la cuenta exige distribución?

        Se comprueba la existencia del campo para no acoplar el módulo a que
        `account_analytic_required` esté instalado.
        """
        if not account or "analytic_policy" not in account._fields:
            return False
        return account.analytic_policy in ANALYTIC_REQUIRED_POLICIES

    def _accounts_requiring_analytic(self, accounts):
        """Subconjunto de cuentas cuya política analítica exige distribución."""
        return accounts.filtered(self._requires_analytic)

    def _collect_period_balances(self, accounts):
        """Saldos del periodo agregados por bucket.

        :return: dict[ClosingBucket, [balance, amount_currency]]
        """
        balances = defaultdict(lambda: [0.0, 0.0])
        if not accounts:
            return balances

        analytic_accounts = accounts.browse()
        if self.analytic_mode == "replicate":
            analytic_accounts = self._accounts_requiring_analytic(accounts)

        # Cuentas sin analítica obligatoria: agregación en la BD (una consulta
        # por modo de detalle, como mucho tres consultas en total).
        grouped_accounts = defaultdict(lambda: accounts.browse())
        for account in accounts - analytic_accounts:
            grouped_accounts[account.closing_detail] |= account
        for detail, group in grouped_accounts.items():
            self._read_grouped_balances(group, detail, balances)

        # Cuentas con analítica obligatoria: `analytic_distribution` es un JSON
        # y no es agrupable por SQL, así que se agrega en Python.
        if analytic_accounts:
            self._read_analytic_balances(analytic_accounts, balances)
        return balances

    def _read_grouped_balances(self, accounts, detail, balances):
        """Agrega saldos con `_read_group` (API de Odoo 17/18)."""
        groupby = ["account_id", "currency_id"]
        detail_field = self._DETAIL_FIELDS.get(detail)
        if detail_field:
            groupby.append(detail_field)

        rows = self.env["account.move.line"]._read_group(
            self._get_move_line_domain(accounts),
            groupby=groupby,
            aggregates=["balance:sum", "amount_currency:sum"],
        )
        for row in rows:
            account, currency = row[0], row[1]
            detail_record = row[2] if detail_field else None
            balance, amount_currency = row[-2], row[-1]
            bucket = ClosingBucket(
                account_id=account.id,
                currency_id=currency.id,
                product_id=detail_record.id if detail == "product" and detail_record else 0,
                partner_id=detail_record.id if detail == "partner" and detail_record else 0,
            )
            balances[bucket][0] += balance
            balances[bucket][1] += amount_currency

    def _read_analytic_balances(self, accounts, balances):
        """Agrega saldos conservando la distribución analítica de origen.

        Nota de rendimiento: se recorren los apuntes uno a uno porque los
        campos JSON no son agrupables en SQL. Se usa `search_fetch` para
        traerlos en una única consulta con sólo las columnas necesarias.
        """
        detail_by_account = {
            account.id: account.closing_detail for account in accounts
        }
        lines = self.env["account.move.line"].search_fetch(
            self._get_move_line_domain(accounts),
            [
                "account_id",
                "currency_id",
                "product_id",
                "partner_id",
                "balance",
                "amount_currency",
                "analytic_distribution",
            ],
        )
        for line in lines:
            detail = detail_by_account.get(line.account_id.id, "none")
            bucket = ClosingBucket(
                account_id=line.account_id.id,
                currency_id=line.currency_id.id,
                product_id=line.product_id.id if detail == "product" else 0,
                partner_id=line.partner_id.id if detail == "partner" else 0,
                analytic_key=self._analytic_key(line.analytic_distribution),
            )
            balances[bucket][0] += line.balance
            balances[bucket][1] += line.amount_currency

    @staticmethod
    def _analytic_key(distribution):
        """Clave canónica y hashable de una distribución analítica."""
        if not distribution:
            return ""
        return json.dumps(distribution, sort_keys=True, separators=(",", ":"))

    # ------------------------------------------------------------------
    # Construcción de los asientos
    # ------------------------------------------------------------------
    def _prepare_closing_moves(self):
        """Prepara los valores de todos los asientos, nivel por nivel."""
        company_currency = self.company_id.currency_id
        accounts = self._get_accounts_to_close()
        if not accounts:
            raise UserError(
                _(
                    "Ninguna cuenta de la compañía %s tiene configurada una "
                    "'Cuenta de Cierre'.",
                    self.company_id.display_name,
                )
            )

        # Los destinos finales de la cadena no se cierran, pero se necesitan en
        # el mapa para resolver `closing_account_id` sin consultas adicionales.
        all_accounts = accounts | accounts.mapped("closing_account_id")
        accounts_by_id = {account.id: account for account in all_accounts}
        balances = self._collect_period_balances(accounts)

        # Descendente: primero el eslabón más lejano del final de la cadena.
        levels = sorted({account.closing_depth for account in accounts}, reverse=True)
        move_vals_list = []
        for level in levels:
            level_account_ids = {
                account.id for account in accounts if account.closing_depth == level
            }
            level_buckets = {
                bucket: amounts
                for bucket, amounts in balances.items()
                if bucket.account_id in level_account_ids
                and not company_currency.is_zero(amounts[0])
            }
            if not level_buckets:
                continue
            move_vals_list += self._prepare_level_moves(
                level, level_buckets, balances, accounts_by_id
            )
        return move_vals_list

    def _prepare_level_moves(self, level, level_buckets, balances, accounts_by_id):
        """Reparte los saldos de un nivel en asientos según `entry_grouping`."""
        partitions = defaultdict(dict)
        for bucket, amounts in level_buckets.items():
            key = self._get_move_key(accounts_by_id[bucket.account_id], amounts[0])
            partitions[key][bucket] = amounts

        move_vals_list = []
        for key in sorted(partitions):
            buckets = partitions[key]
            lines = self._prepare_move_lines(buckets, balances, accounts_by_id)
            if not lines:
                continue
            move_vals_list.append(
                self._prepare_move_vals(level, key, lines, buckets, accounts_by_id)
            )
        return move_vals_list

    def _get_move_key(self, account, balance):
        """Clave de agrupación de asientos dentro de un mismo nivel."""
        if self.entry_grouping == "level":
            return ("", "")
        account_class = self._get_account_class(account)
        if self.entry_grouping == "class":
            return (account_class, "")
        return (account_class, "positive" if balance >= 0 else "negative")

    def _get_account_class(self, account):
        """Clase PCGE de la cuenta a partir del primer dígito del código."""
        code = (account.with_company(self.company_id).code or "").strip()
        first_digit = code[:1]
        if first_digit in BALANCE_CLASSES:
            return "balance"
        if first_digit in RESULT_CLASSES:
            return "result"
        return "other"

    def _prepare_move_lines(self, buckets, balances, accounts_by_id):
        """Líneas de un asiento: cuentas cerradas + contrapartidas agregadas.

        Además propaga el importe transferido al bucket de la cuenta destino,
        de modo que el nivel siguiente de la cadena vea ese saldo.
        """
        company_currency = self.company_id.currency_id
        lines = []
        counterparts = defaultdict(lambda: [0.0, 0.0])

        for bucket, (raw_balance, amount_currency) in buckets.items():
            balance = company_currency.round(raw_balance)
            if company_currency.is_zero(balance):
                continue
            account = accounts_by_id[bucket.account_id]
            target = account.closing_account_id

            # La línea de la cuenta que se cierra revierte su saldo.
            lines.append(
                self._prepare_line_vals(
                    bucket.account_id,
                    -balance,
                    -amount_currency,
                    bucket.currency_id,
                    self.line_label,
                    bucket=bucket,
                )
            )

            # La distribución analítica sólo se arrastra a la contrapartida
            # cuando la cuenta destino la exige: así se evita el bypass de la
            # validación sin ensuciar con analítica cuentas que no la piden.
            target_analytic_key = (
                bucket.analytic_key if self._requires_analytic(target) else ""
            )

            # Contrapartida: débitos y créditos se acumulan por separado para
            # que el asiento muestre ambos lados sin compensarse entre sí.
            side = "debit" if balance > 0 else "credit"
            counterpart_key = (
                target.id,
                bucket.currency_id,
                side,
                target_analytic_key,
            )
            counterparts[counterpart_key][0] += balance
            counterparts[counterpart_key][1] += amount_currency

            # Propagación al siguiente nivel de la cadena.
            target_bucket = ClosingBucket(
                account_id=target.id,
                currency_id=bucket.currency_id,
                analytic_key=target_analytic_key,
            )
            balances[target_bucket][0] += balance
            balances[target_bucket][1] += amount_currency

        counterpart_label = _("Cierre - %s", self.line_label)
        for counterpart_key, (balance, amount_currency) in counterparts.items():
            if company_currency.is_zero(balance):
                continue
            target_id, currency_id, _side, analytic_key = counterpart_key
            lines.append(
                self._prepare_line_vals(
                    target_id,
                    balance,
                    amount_currency,
                    currency_id,
                    counterpart_label,
                    bucket=ClosingBucket(
                        account_id=target_id,
                        currency_id=currency_id,
                        analytic_key=analytic_key,
                    ),
                )
            )
        return lines

    def _prepare_line_vals(
        self, account_id, balance, amount_currency, currency_id, label, bucket=None
    ):
        """Valores de una línea de asiento a partir de un saldo ya orientado."""
        vals = {
            "account_id": account_id,
            "name": label,
            "debit": balance if balance > 0 else 0.0,
            "credit": -balance if balance < 0 else 0.0,
        }
        # Sólo se informa la moneda cuando es realmente extranjera: si es la de
        # la compañía, Odoo calcula `amount_currency` a partir del balance.
        if currency_id and currency_id != self.company_id.currency_id.id:
            vals["currency_id"] = currency_id
            vals["amount_currency"] = amount_currency
        if bucket:
            if bucket.product_id:
                vals["product_id"] = bucket.product_id
            if bucket.partner_id:
                vals["partner_id"] = bucket.partner_id
            if bucket.analytic_key:
                vals["analytic_distribution"] = json.loads(bucket.analytic_key)
        return vals

    def _prepare_move_vals(self, level, key, lines, buckets, accounts_by_id):
        account_class, sign = key
        prefixes = sorted(
            {
                (accounts_by_id[bucket.account_id].with_company(self.company_id).code or "")[:2]
                for bucket in buckets
            }
            - {""}
        )
        return {
            "move_type": "entry",
            "journal_id": self.journal_id.id,
            "company_id": self.company_id.id,
            "date": self.closing_date,
            "ref": self._build_reference(level, account_class, sign, prefixes),
            "is_closing_entry": True,
            "closing_level": level,
            "closing_date_from": self.date_from,
            "closing_date_to": self.date_to,
            "line_ids": [Command.create(vals) for vals in lines],
        }

    def _build_reference(self, level, account_class, sign, prefixes):
        # Se referencia el nivel real de la cadena (no un contador de pasos):
        # así la glosa sigue siendo válida aunque algún nivel no genere asiento.
        parts = [_("Cierre nivel %s", level)]
        if account_class:
            parts.append(ACCOUNT_CLASS_LABELS[account_class])
        if prefixes:
            parts.append(", ".join(prefixes))
        if sign:
            parts.append(
                _("Saldos positivos") if sign == "positive" else _("Saldos negativos")
            )
        return " · ".join(parts)

    # ------------------------------------------------------------------
    # Confirmación de analítica y mensajes
    # ------------------------------------------------------------------
    def _get_accounts_missing_analytic(self, move_vals_list):
        """Cuentas con analítica obligatoria cuyas líneas irían sin distribución."""
        account_ids = {
            command[2]["account_id"]
            for move_vals in move_vals_list
            for command in move_vals["line_ids"]
            if not command[2].get("analytic_distribution")
        }
        if not account_ids:
            return self.env["account.account"].browse()
        accounts = self.env["account.account"].browse(sorted(account_ids))
        return self._accounts_requiring_analytic(accounts)

    def _action_confirm_missing_analytic(self, accounts):
        message = _(
            "Las siguientes cuentas exigen distribución analítica y el asiento de "
            "cierre se generaría sin ella. Confirme si desea crearlo de todos "
            "modos:\n\n- %s",
            "\n- ".join(accounts.mapped("display_name")),
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Confirmación"),
            "res_model": "closing.entry.confirm.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_closing_wizard_id": self.id,
                "default_message": message,
            },
        }

    def _get_existing_closing_moves(self):
        Move = self.env["account.move"]
        return Move.search(
            Move._get_closing_entry_domain(
                self.company_id, self.date_from, self.date_to
            )
        )

    def _get_nothing_to_close_message(self, existing_moves):
        if existing_moves:
            return _(
                "No quedan saldos pendientes de cierre entre %(date_from)s y "
                "%(date_to)s.\n\n"
                "Ya existen %(count)s asiento(s) de cierre para ese periodo, que "
                "el cálculo ya ha tenido en cuenta. Si desea regenerarlos, marque "
                "«Reemplazar borradores existentes» (los asientos publicados no se "
                "eliminan; deberá revertirlos manualmente).",
                date_from=self.date_from,
                date_to=self.date_to,
                count=len(existing_moves),
            )
        return _(
            "No se encontraron saldos por cerrar entre %(date_from)s y "
            "%(date_to)s. Verifique el periodo, el estado de los asientos y la "
            "configuración de 'Cuenta de Cierre' en el plan contable.",
            date_from=self.date_from,
            date_to=self.date_to,
        )

    def _action_open_moves(self, moves):
        action = self._get_moves_action()
        if len(moves) > 1:
            action["domain"] = [("id", "in", moves.ids)]
        else:
            action.update(
                {
                    "views": [(False, "form")],
                    "view_mode": "form",
                    "res_id": moves.id,
                }
            )
        return action
