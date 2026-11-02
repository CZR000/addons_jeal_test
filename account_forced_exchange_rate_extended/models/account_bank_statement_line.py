from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

from .exchange_rate_mixin import (
    CASE_COUNTERPART,
    CASE_LIQUIDITY,
    CASE_NONE,
    RATE_DIGITS,
    RATE_TYPE_PURCHASE,
    RATE_TYPE_SALE,
)


class AccountBankStatementLine(models.Model):
    """
    Transacciones bancarias contabilizadas a un tipo de cambio forzado.

    Según la moneda del diario y si el banco informó una tercera moneda
    (``foreign_currency_id``), la tasa se aplica en un sitio distinto:

    ==============  ==========  ===============  ===============================
    Diario          3ª moneda   Caso             Dónde aplica la tasa
    ==============  ==========  ===============  ===============================
    = compañía      no          ``counterpart``  diferencia de cambio al conciliar
    ≠ compañía      no          ``liquidity``    pata bancaria del asiento
    cualquiera      sí          ``none``         no aplica, el campo se oculta
    ==============  ==========  ===============  ===============================

    El caso ``none`` se excluye por seguridad contable: la tasa del asiento se
    aplica a todas las líneas en moneda extranjera, y revalorizaría también la
    pata de esa tercera moneda descuadrando el asiento.
    """

    _name = "account.bank.statement.line"
    _inherit = ["account.bank.statement.line", "exchange.rate.mixin"]

    amount_company_currency = fields.Monetary(
        string="Importe en Soles",
        currency_field="company_currency_id",
        compute="_compute_amount_company_currency",
        help="""
            Importe de la transacción convertido a la moneda de la compañía con
            el tipo de cambio aplicado, ya redondeado.\n
            Sirve para ver cuánto sale la operación antes de conciliar.
        """,
    )

    @api.depends("amount", "exchange_rate", "currency_id", "company_currency_id")
    def _compute_amount_company_currency(self):
        """
        Convierte el importe de la transacción a moneda de la compañía.
        """
        for st_line in self:
            if st_line.currency_id == st_line.company_currency_id:
                st_line.amount_company_currency = st_line.amount
            else:
                st_line.amount_company_currency = st_line._convert_to_company_currency(
                    st_line.amount
                )

    # -------------------------------------------------------------------------
    # CONTRATO DEL MIXIN DE TIPO DE CAMBIO
    # -------------------------------------------------------------------------
    def _get_exchange_rate_context(self):
        """
        Monedas y fecha con que se calcula la tasa.

        Returns:
            tuple: (compañía, moneda_compañía, moneda_diario, fecha).
        """
        self.ensure_one()
        # currency_id es la moneda del diario: la de la pata de liquidez, que es
        # la que Odoo tiene que convertir.
        return self.company_id, self.company_currency_id, self.currency_id, self.date

    @api.model
    def _get_exchange_rate_depends(self):
        """
        Campos que alteran la tasa o la casuística.

        Returns:
            tuple: nombres de campo para los @api.depends del mixin.
        """
        return ("company_id", "currency_id", "foreign_currency_id", "date")

    @api.model
    def _get_exchange_rate_type_depends(self):
        """
        Campos que determinan si la operación es compra o venta.

        Returns:
            tuple: los de la tasa más ``amount``, cuyo signo fija el sentido.
        """
        return self._get_exchange_rate_depends() + ("amount",)

    def _get_default_exchange_rate_type(self):
        """
        Propone compra para lo que ingresa y venta para lo que sale.

        Criterio SUNAT: los ingresos se valorizan al tipo de cambio compra y los
        egresos al de venta. El usuario puede sobrescribirlo en el widget.

        Returns:
            str: RATE_TYPE_PURCHASE, RATE_TYPE_SALE, o False si no hay conversión.
        """
        self.ensure_one()
        if self._get_exchange_rate_case() == CASE_NONE:
            return False
        return RATE_TYPE_PURCHASE if self.amount >= 0.0 else RATE_TYPE_SALE

    def _get_exchange_rate_case(self):
        """
        Clasifica la transacción según la tabla de la clase.

        Returns:
            str: CASE_NONE, CASE_LIQUIDITY o CASE_COUNTERPART.
        """
        self.ensure_one()
        if self.foreign_currency_id:
            return CASE_NONE
        if self.currency_id and self.currency_id != self.company_currency_id:
            return CASE_LIQUIDITY
        return CASE_COUNTERPART

    def _forces_liquidity_valuation(self):
        """
        Indica si la tasa revaloriza la pata bancaria del asiento.

        Returns:
            bool: True si la tasa propia difiere de la estándar y el caso es
            ``liquidity``.
        """
        self.ensure_one()
        return (
            self._overrides_odoo_rate()
            and self._get_exchange_rate_case() == CASE_LIQUIDITY
        )

    def _forces_counterpart_valuation(self):
        """
        Indica si la tasa valoriza las contrapartidas al conciliar.

        Returns:
            bool: True si la tasa propia difiere de la estándar y el caso es
            ``counterpart``.
        """
        self.ensure_one()
        return (
            self._overrides_odoo_rate()
            and self._get_exchange_rate_case() == CASE_COUNTERPART
        )

    # -------------------------------------------------------------------------
    # AYUDANTES
    # -------------------------------------------------------------------------
    @staticmethod
    def _set_balance_in_line_vals(line_vals, balance):
        """
        Reescribe el par debe/haber de un dict de account.move.line.

        Args:
            line_vals (dict): valores del apunte; se modifica en sitio.
            balance (float): importe con signo en moneda de compañía.
        """
        line_vals["debit"] = balance if balance > 0.0 else 0.0
        line_vals["credit"] = -balance if balance < 0.0 else 0.0

    def _forced_rate_differs(self, new_rate):
        """
        Indica si alguna transacción cambiaría de tasa con ese valor.

        Args:
            new_rate (float): tasa que se pretende escribir.

        Returns:
            bool: True si al menos una difiere más allá de RATE_DIGITS.
        """
        return any(
            float_compare(
                st_line.forced_exchange_rate, new_rate, precision_digits=RATE_DIGITS
            )
            for st_line in self
        )

    def _check_rate_type_is_editable(self, new_type):
        """
        Impide cambiar compra/venta en una transacción ya conciliada.

        Cambiar el tipo cambia la tasa leída y, con ella, la valorización del
        asiento. Misma protección que para la tasa forzada.

        Args:
            new_type (str): tipo que se pretende escribir.

        Raises:
            UserError: si alguna línea conciliada cambiaría de tipo.
        """
        locked_lines = self.filtered(
            lambda st_line: st_line.is_reconciled
            and st_line.exchange_rate_type != new_type
        )
        if locked_lines:
            raise UserError(
                _(
                    "No se puede cambiar el tipo de cambio SBS de una transacción "
                    "bancaria ya conciliada: %(transactions)s.\n"
                    "Revierta primero la conciliación.",
                    transactions=", ".join(locked_lines.mapped("display_name")),
                )
            )

    def _check_forced_rate_is_editable(self, new_rate):
        """
        Impide cambiar la tasa de una transacción ya conciliada.

        Cambiarla reconstruye el asiento y elimina sus contrapartidas, lo que
        desharía la conciliación en silencio. Las vistas ya lo impiden; esto
        protege el ORM: importaciones, actualizaciones masivas y scripts.

        Args:
            new_rate (float): tasa que se pretende escribir.

        Raises:
            UserError: si alguna línea conciliada cambiaría de tasa.
        """
        locked_lines = self.filtered(
            lambda st_line: st_line.is_reconciled
            and float_compare(
                st_line.forced_exchange_rate, new_rate, precision_digits=RATE_DIGITS
            )
        )
        if locked_lines:
            raise UserError(
                _(
                    "No se puede cambiar el tipo de cambio de una transacción bancaria "
                    "ya conciliada: %(transactions)s.\n"
                    "Revierta primero la conciliación y vuelva a fijar la tasa.",
                    transactions=", ".join(locked_lines.mapped("display_name")),
                )
            )

    def _sync_forced_rate_to_move(self):
        """
        Refleja la tasa en el asiento, en convención inversa.

        El asiento es de donde el resto de la contabilidad (reportes, PLE) lee
        la tasa, y además Odoo revalúa sus líneas en moneda extranjera con
        ``balance = amount_currency / currency_rate``, que sale de este campo.
        """
        # Se agrupa por tasa para que importar un extracto no haga una escritura
        # por línea.
        moves_by_rate = defaultdict(lambda: self.env["account.move"])
        for st_line in self:
            rate = (
                st_line._get_inverse_exchange_rate()
                if st_line._overrides_odoo_rate()
                else 0.0
            )
            moves_by_rate[rate] |= st_line.move_id

        for rate, moves in moves_by_rate.items():
            # Comparación con tolerancia: el campo destino guarda 12 decimales,
            # comparar en crudo daría "distinto" siempre.
            outdated_moves = moves.filtered(
                lambda move: float_compare(
                    move.to_force_exchange_rate, rate, precision_digits=RATE_DIGITS
                )
            )
            if outdated_moves:
                outdated_moves.to_force_exchange_rate = rate

    # -------------------------------------------------------------------------
    # MÉTODOS DE BAJO NIVEL
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """
        Crea las transacciones y alinea la tasa de sus asientos.

        Args:
            vals_list (list): diccionarios de creación.

        Returns:
            recordset: las account.bank.statement.line creadas.
        """
        st_lines = super().create(vals_list)
        # El asiento puede traer una tasa propagada por contexto
        # desde account_field_to_force_exchange_rate y hay que limpiarla.
        st_lines._sync_forced_rate_to_move()
        return st_lines

    def write(self, vals):
        """
        Escribe y propaga al asiento los cambios de tasa forzada.

        Args:
            vals (dict): valores a escribir.

        Returns:
            bool: True.

        Raises:
            UserError: si se cambia la tasa de una transacción conciliada.
        """
        # Sin cambio real se descarta la clave: dejarla pasar reconstruiría el
        # asiento igualmente y en una conciliada borraría sus contrapartidas.
        if "forced_exchange_rate" in vals and not self._forced_rate_differs(
            vals["forced_exchange_rate"]
        ):
            vals = {
                key: value
                for key, value in vals.items()
                if key != "forced_exchange_rate"
            }

        if "forced_exchange_rate" in vals:
            self._check_forced_rate_is_editable(vals["forced_exchange_rate"])
        if "exchange_rate_type" in vals:
            self._check_rate_type_is_editable(vals["exchange_rate_type"])

        res = super().write(vals)

        # El tipo también mueve la tasa leída, así que el asiento debe seguirla.
        if {"forced_exchange_rate", "exchange_rate_type"} & vals.keys():
            self._sync_forced_rate_to_move()
        return res

    # -------------------------------------------------------------------------
    # MÉTODOS DE NEGOCIO
    # -------------------------------------------------------------------------
    def _prepare_move_line_default_vals(self, counterpart_account_id=None):
        """
        Contabiliza el par liquidez/transitoria a la tasa forzada.

        Único punto donde Odoo 18 convierte el importe del diario a moneda de
        compañía, y por eso el único override que necesita el caso ``liquidity``.

        Args:
            counterpart_account_id (int, optional): cuenta de contrapartida en
                lugar de la transitoria del diario.

        Returns:
            list: [valores_liquidez, valores_contrapartida].
        """
        line_vals_list = super()._prepare_move_line_default_vals(counterpart_account_id)
        if not self._forces_liquidity_valuation():
            return line_vals_list

        # amount está en moneda del diario, la extranjera aquí: la tasa multiplica.
        company_amount = self._convert_to_company_currency(self.amount)

        # Contrato de Odoo: [línea de liquidez, contrapartida].
        self._set_balance_in_line_vals(line_vals_list[0], company_amount)
        self._set_balance_in_line_vals(line_vals_list[1], -company_amount)
        return line_vals_list

    # -------------------------------------------------------------------------
    # SINCRONIZACIÓN account.bank.statement.line <-> account.move
    # -------------------------------------------------------------------------
    def _synchronize_to_moves(self, changed_fields):
        """
        Reconstruye los apuntes cuando la tasa revaloriza la pata bancaria.

        Args:
            changed_fields (set): campos modificados.

        Returns:
            None
        """
        # Declarar que también cambió `amount` reutiliza la lista blanca de
        # disparadores del propio Odoo en vez de duplicarla aquí. Solo en el
        # caso `liquidity`: en el otro la línea del banco no cambia y
        # reconstruir el asiento borraría apuntes sin ganancia.
        if "forced_exchange_rate" in changed_fields and any(
            st_line._forces_liquidity_valuation() for st_line in self
        ):
            changed_fields = set(changed_fields) | {"amount"}
        return super()._synchronize_to_moves(changed_fields)
