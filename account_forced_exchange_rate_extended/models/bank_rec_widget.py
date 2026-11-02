from odoo import models

from .exchange_rate_mixin import CASE_LIQUIDITY, RATE_EPSILON


class BankRecWidget(models.Model):
    """
    Edición del tipo de cambio dentro del widget de conciliación bancaria.

    Se apoya solo en mecanismos nativos de Odoo 18: el despachador genérico
    ``_js_action_line_changed`` recibe el cambio y los métodos de recálculo del
    propio widget lo propagan. No se parchea nada del JavaScript estándar.

    El cálculo de la diferencia de cambio vive en
    ``exchange.rate.reconcile.mixin`` para poder reutilizarlo desde cualquier
    otro asistente de conciliación.

    La pata bancaria conserva siempre ``importe x tasa``, el mismo número que da
    la calculadora. Si la factura quedó contabilizada a otro valor —convierte y
    redondea línea a línea, mientras que el extracto convierte el total de una
    vez—, esos céntimos se asientan como diferencia de cambio, que es lo que
    son. No se absorben en el banco: eso alteraría el valor de la cuenta
    bancaria y contradice lo que el contador calcula a mano.
    """

    _name = "bank.rec.widget"
    _inherit = ["bank.rec.widget", "exchange.rate.reconcile.mixin"]

    # -------------------------------------------------------------------------
    # CONTRATO DEL MIXIN DE CONCILIACIÓN
    # -------------------------------------------------------------------------
    def _get_exchange_rate_source(self):
        """
        Registro que lleva la tasa de la operación.

        Returns:
            recordset: la account.bank.statement.line montada en el widget.
        """
        self.ensure_one()
        return self.st_line_id

    # -------------------------------------------------------------------------
    # DIFERENCIA DE CAMBIO
    # -------------------------------------------------------------------------
    def _lines_get_account_balance_exchange_diff(
        self, currency, balance, amount_currency
    ):
        """
        Valoriza las contrapartidas en moneda extranjera a la tasa forzada.

        Cuando la transacción está en moneda de compañía —un cobro en soles que
        paga una factura en dólares—, Odoo valoriza el apunte en dólares al tipo
        de cambio oficial de la fecha, y esa conversión es lo único que
        determina la diferencia de cambio. Aquí se reemplaza por la tasa que
        digitó el contador.

        Args:
            currency (recordset): moneda del apunte a valorizar.
            balance (float): importe del apunte en moneda de compañía.
            amount_currency (float): importe del apunte en su propia moneda.

        Returns:
            tuple: (cuenta de diferencia de cambio, importe de la diferencia).

        Raises:
            UserError: si faltan las cuentas de diferencia de cambio.
        """
        self.ensure_one()
        # Si la transacción ya está en moneda extranjera, la tasa llegó por la
        # pata de liquidez y aplicarla otra vez la duplicaría.
        forces_counterpart = (
            self.st_line_id._forces_counterpart_valuation()
            and currency != self.company_currency_id
            and self.transaction_currency_id == self.company_currency_id
        )
        if forces_counterpart:
            return self._prepare_forced_exchange_diff(
                balance, amount_currency, self.company_id
            )
        return super()._lines_get_account_balance_exchange_diff(
            currency, balance, amount_currency
        )

    # -------------------------------------------------------------------------
    # ACTUALIZACIÓN DE LÍNEAS
    # -------------------------------------------------------------------------
    def _line_value_changed_exchange_rate_type(self, line):
        """
        Cambia entre tipo de cambio compra y venta mientras se concilia.

        Lo invoca el despachador ``_js_action_line_changed``.

        Args:
            line (recordset): línea editada; se ignora si no es la de liquidez.
        """
        self.ensure_one()
        if line.flag != "liquidity":
            return

        self.st_line_id.exchange_rate_type = line.exchange_rate_type
        self._refresh_after_exchange_rate_change()

    def _line_value_changed_forced_exchange_rate(self, line):
        """
        Aplica una tasa digitada por el contador mientras concilia.

        Lo invoca el despachador ``_js_action_line_changed``.

        Args:
            line (recordset): línea editada; se ignora si no es la de liquidez.
        """
        self.ensure_one()
        if line.flag != "liquidity":
            return

        rate = line.forced_exchange_rate
        self.st_line_id.forced_exchange_rate = rate if rate > RATE_EPSILON else 0.0
        self._refresh_after_exchange_rate_change()

    def _refresh_after_exchange_rate_change(self):
        """
        Propaga al panel un cambio de tasa, con el alcance mínimo necesario.
        """
        self.ensure_one()
        if self.st_line_id._get_exchange_rate_case() == CASE_LIQUIDITY:
            # Cambia el valor de todo el asiento: se reconstruye el widget desde
            # la transacción, igual que hace Odoo al editar el importe.
            self._action_reload_liquidity_line()
            self.return_todo_command = {"reset_global_info": True, "reset_record": True}
            return

        # Solo se mueve la diferencia de cambio: recalcularla en sitio conserva
        # los apuntes que el contador ya montó.
        self._lines_recompute_exchange_diff(
            self.line_ids.filtered(lambda x: x.flag == "new_aml")
        )
        self._lines_add_auto_balance_line()

    # -------------------------------------------------------------------------
    # VALIDACIÓN
    # -------------------------------------------------------------------------
    def _action_validate(self):
        """
        Valida la conciliación tras comprobar la coherencia de la tasa.

        Raises:
            UserError: si una sola tasa tendría que valorizar apuntes en más de
                una moneda extranjera.
        """
        self.ensure_one()
        if self.st_line_id._overrides_odoo_rate():
            currencies = self.line_ids.filtered(
                lambda x: x.flag == "new_aml"
            ).currency_id
            self._check_forced_rate_covers_a_single_currency(
                currencies - self.company_currency_id
            )
        return super()._action_validate()
