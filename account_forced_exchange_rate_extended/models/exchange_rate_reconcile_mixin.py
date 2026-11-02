from odoo import _, models
from odoo.exceptions import UserError


class ExchangeRateReconcileMixin(models.AbstractModel):
    """
    Diferencia de cambio calculada a un tipo de cambio forzado.

    Complementa a ``exchange.rate.mixin``: aquel resuelve *cuál* es la tasa de
    un documento, este *qué diferencia de cambio* produce al conciliarlo contra
    apuntes en moneda extranjera.

    El modelo heredero debe implementar :meth:`_get_exchange_rate_source`.
    Ver el README para un ejemplo completo.
    """

    _name = "exchange.rate.reconcile.mixin"
    _description = "Mixin de Diferencia de Cambio en Conciliación"

    # -------------------------------------------------------------------------
    # CONTRATO A IMPLEMENTAR
    # -------------------------------------------------------------------------
    def _get_exchange_rate_source(self):
        """
        Registro que lleva el tipo de cambio de la operación.

        Returns:
            recordset: un registro único que hereda exchange.rate.mixin.

        Raises:
            NotImplementedError: si el heredero no lo implementa.
        """
        raise NotImplementedError(
            "El modelo %s debe implementar '_get_exchange_rate_source'." % self._name
        )

    # -------------------------------------------------------------------------
    # AYUDANTES DE NEGOCIO
    # -------------------------------------------------------------------------
    def _get_exchange_diff_account(self, exchange_diff_balance, company):
        """
        Selecciona la cuenta de diferencia de cambio según el signo.

        Args:
            exchange_diff_balance (float): diferencia en moneda de compañía;
                positiva es pérdida, negativa es ganancia.
            company (recordset): compañía de la que se toman las cuentas.

        Returns:
            recordset: account.account de gasto o de ingreso por diferencia.

        Raises:
            UserError: si la compañía no tiene configurada esa cuenta.
        """
        account = (
            company.expense_currency_exchange_account_id
            if exchange_diff_balance > 0.0
            else company.income_currency_exchange_account_id
        )
        if not account:
            raise UserError(
                _(
                    "Configure las cuentas de diferencia de cambio en la compañía "
                    "%(company)s antes de forzar un tipo de cambio.",
                    company=company.display_name,
                )
            )
        return account

    def _prepare_forced_exchange_diff(self, balance, amount_currency, company):
        """
        Valoriza una contrapartida en moneda extranjera a la tasa forzada.

        Args:
            balance (float): importe con que quedó contabilizado en su origen.
            amount_currency (float): importe del apunte en su propia moneda.
            company (recordset): compañía de la operación.

        Returns:
            tuple: (cuenta, diferencia). Cuenta vacía y 0.0 si no hay diferencia.

        Raises:
            UserError: si faltan las cuentas de diferencia de cambio.
        """
        self.ensure_one()
        source = self._get_exchange_rate_source()
        company_currency = company.currency_id

        # La diferencia es lo que separa el valor a la tasa forzada del valor con
        # que la factura quedó contabilizada.
        origin_balance = source._convert_to_company_currency(amount_currency)
        exchange_diff_balance = origin_balance - balance
        if company_currency.is_zero(exchange_diff_balance):
            return self.env["account.account"], 0.0

        return (
            self._get_exchange_diff_account(exchange_diff_balance, company),
            exchange_diff_balance,
        )

    def _check_forced_rate_covers_a_single_currency(self, currencies):
        """
        Verifica que una sola tasa no valorice dos monedas extranjeras.

        Args:
            currencies (recordset): monedas extranjeras de las contrapartidas,
                ya sin la moneda de la compañía.

        Raises:
            UserError: si hay más de una moneda extranjera.
        """
        self.ensure_one()
        if len(currencies) > 1:
            raise UserError(
                _(
                    "Un único tipo de cambio forzado no puede valorizar apuntes en "
                    "%(currencies)s a la vez.\n"
                    "Concilie una moneda extranjera por vez, o deje vacío el campo "
                    "Forzar T.C.",
                    currencies=", ".join(currencies.mapped("name")),
                )
            )
