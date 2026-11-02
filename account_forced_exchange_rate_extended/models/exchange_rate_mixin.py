from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero

# Umbral por debajo del cual una tasa se considera "sin definir" y no "cero".
RATE_EPSILON = 1e-12

# Decimales con que account.move.to_force_exchange_rate almacena la tasa.
RATE_DIGITS = 12

# Precisión con que se compara una tasa contra 1.0 para detectar que el módulo
# de carga no encontró fila y devolvió su valor por defecto.
RATE_MATCH_DIGITS = 6

# Casuística de forzado: cada registro cae en exactamente uno de estos casos.
CASE_NONE = "none"
CASE_LIQUIDITY = "liquidity"
CASE_COUNTERPART = "counterpart"

EXCHANGE_RATE_CASES = [
    (CASE_NONE, "No aplica"),
    (CASE_LIQUIDITY, "Valoriza la operación"),
    (CASE_COUNTERPART, "Valoriza la contrapartida"),
]

# Tipo de cambio publicado por la SBS. Las claves coinciden con las del campo
# `exchange_rate` de res.currency.rate que aporta el módulo de carga de tasas.
RATE_TYPE_PURCHASE = "purchase"
RATE_TYPE_SALE = "sale"

EXCHANGE_RATE_TYPES = [
    (RATE_TYPE_PURCHASE, "Compra"),
    (RATE_TYPE_SALE, "Venta"),
]

# Método que el módulo de carga SBS añade a res.currency para leer la tasa de
# compra.
# La de venta no necesita método propio: el módulo la deja como tasa por defecto
# de Odoo, así que la conversión estándar ya la devuelve.
# Mientras el método no exista, todo cae en la conversión estándar.
PURCHASE_RATE_METHOD = "_get_conversion_purchase_rate"


class ExchangeRateMixin(models.AbstractModel):
    """
    Tipo de cambio de la fecha y tasa forzada, para modelos con dos monedas.

    Todas las tasas son **comerciales**: unidades de moneda de la compañía por
    una de la moneda extranjera (3.7500 PEN por 1 USD). Es la convención
    contraria a ``account.move.to_force_exchange_rate``, que guarda la inversa.
    """

    _name = "exchange.rate.mixin"
    _description = "Mixin de Tipo de Cambio"

    # -------------------------------------------------------------------------
    # CAMPOS
    # -------------------------------------------------------------------------
    exchange_rate = fields.Float(
        string="Tipo de Cambio",
        digits=0,
        compute="_compute_exchange_rate",
        store=True,
        help="""
            Tipo de cambio aplicado a esta operación.\n
            Si dejó vacío 'Forzar T.C.', es el tipo de cambio oficial de la fecha del documento. \n
            Si lo digitó, es el suyo.
        """,
    )

    forced_exchange_rate = fields.Float(
        string="Forzar T.C.",
        digits=0,
        help="""
            Digite aquí el tipo de cambio que quiere aplicar en lugar del
            oficial de la fecha, por ejemplo para cuadrar una conciliación
            con el tipo de cambio real que le dio el banco.\n
            Déjelo vacío para usar el oficial. Se expresa en soles por dólar
            (3.7500), no al revés.
        """,
    )

    exchange_rate_type = fields.Selection(
        selection=EXCHANGE_RATE_TYPES,
        string="Modalidad del tipo de cambio",
        compute="_compute_exchange_rate_type",
        store=True,
        readonly=False,
        help="Indica con qué tipo de cambio de la que se valoriza la operación: "
        "compra para lo que ingresa, venta para lo que sale.\n"
        "Al cambiarlo se vuelve a leer el tipo de cambio de la fecha.",
    )

    exchange_rate_case = fields.Selection(
        selection=EXCHANGE_RATE_CASES,
        string="Casuística del T.C.",
        compute="_compute_exchange_rate_case",
        help="""
            Campo técnico: resume dónde aplica la tasa forzada. Las vistas lo
            usan en sus modificadores para no repetir la regla de monedas.
        """,
    )

    # -------------------------------------------------------------------------
    # CONTRATO A IMPLEMENTAR
    # -------------------------------------------------------------------------
    def _get_exchange_rate_context(self):
        """
        Datos con que se resuelve la tasa del registro.

        Returns:
            tuple: (compañía, moneda_compañía, moneda_extranjera, fecha).

        Raises:
            NotImplementedError: si el heredero no lo implementa.
        """
        raise NotImplementedError(
            "El modelo %s debe implementar '_get_exchange_rate_context'." % self._name
        )

    @api.model
    def _get_exchange_rate_depends(self):
        """
        Campos del heredero que alteran la tasa o la casuística.

        Returns:
            tuple: nombres de campo para los @api.depends del mixin.
        """
        return ()

    @api.model
    def _get_exchange_rate_type_depends(self):
        """
        Campos del heredero que determinan el tipo de cambio SBS por defecto.

        Returns:
            tuple: nombres de campo; por defecto los mismos de la tasa.
        """
        return self._get_exchange_rate_depends()

    def _get_default_exchange_rate_type(self):
        """
        Tipo de cambio SBS que corresponde por defecto a la operación.

        La implementación base conserva lo que ya haya: devolver False aquí
        borraría la elección manual en cada recálculo de los herederos que no
        sobreescriban este método.

        Returns:
            str: RATE_TYPE_PURCHASE, RATE_TYPE_SALE o False si no aplica.
        """
        self.ensure_one()
        return self.exchange_rate_type

    def _get_exchange_rate_case(self):
        """
        Clasifica el registro en la casuística de forzado.

        Returns:
            str: CASE_NONE si no hay conversión, CASE_LIQUIDITY si la hay.
        """
        self.ensure_one()
        _company, company_currency, foreign_currency, _date = (
            self._get_exchange_rate_context()
        )
        if (
            not company_currency
            or not foreign_currency
            or company_currency == foreign_currency
        ):
            return CASE_NONE
        return CASE_LIQUIDITY

    # -------------------------------------------------------------------------
    # AYUDANTES DE NEGOCIO
    # -------------------------------------------------------------------------
    def _is_exchange_rate_forceable(self):
        """
        Indica si forzar una tasa cambiaría algo. Gobierna la visibilidad.

        Returns:
            bool: True si el registro admite tasa forzada.
        """
        self.ensure_one()
        return self._get_exchange_rate_case() != CASE_NONE

    def _is_forcing_exchange_rate(self):
        """
        Indica si hay una tasa forzada utilizable.

        Returns:
            bool: True si hay tasa digitada y el registro admite forzarla.
        """
        self.ensure_one()
        return (
            self.forced_exchange_rate > RATE_EPSILON
            and self._is_exchange_rate_forceable()
        )

    def _get_market_exchange_rate(self, market_rates=None):
        """
        Tipo de cambio oficial de la fecha (SBS), ignorando el forzado.

        Args:
            market_rates (dict, optional): memoria compartida entre registros
                para evitar una consulta por registro (N+1).

        Returns:
            float: moneda de compañía por unidad extranjera; 1.0 si no hay
            conversión.
        """
        self.ensure_one()
        company, company_currency, foreign_currency, date = (
            self._get_exchange_rate_context()
        )
        if (
            not company_currency
            or not foreign_currency
            or company_currency == foreign_currency
        ):
            return 1.0

        date = date or fields.Date.context_today(self)
        if market_rates is None:
            market_rates = {}
        # El tipo entra en la clave: dos operaciones de la misma fecha y moneda
        # con tipos distintos tienen tasas distintas.
        key = (
            company.id,
            company_currency.id,
            foreign_currency.id,
            date,
            self.exchange_rate_type,
        )
        if key not in market_rates:
            # Tasa compra/venta si el módulo de carga SBS ya la publica; si no,
            # una unidad de moneda extranjera por la conversión estándar.
            market_rates[key] = (
                self._get_typed_market_exchange_rate(foreign_currency, company, date)
                or foreign_currency._convert(
                    from_amount=1.0,
                    to_currency=company_currency,
                    company=company,
                    date=date,
                    round=False,
                )
                or 1.0
            )
        return market_rates[key]

    def _get_typed_market_exchange_rate(self, foreign_currency, company, date):
        """Tasa de compra publicada para esa fecha.

        Devuelve 0.0 cuando no hay tasa de compra utilizable, de modo que el
        llamador cae en la conversión estándar de Odoo: sin el módulo de carga
        SBS, o con él instalado pero sin fila de compra para esa fecha.

        Args:
            foreign_currency (recordset): moneda extranjera de la operación.
            company (recordset): compañía de la operación.
            date (date): fecha con que se busca la tasa.

        Returns:
            float: moneda de compañía por unidad extranjera; 0.0 si no aplica.
        """
        self.ensure_one()
        if not self._uses_purchase_rate():
            return 0.0

        _company, company_currency, _foreign, _date = self._get_exchange_rate_context()
        Currency = self.env["res.currency"]
        # El método devuelve la tasa inversa, igual que `_get_conversion_rate`.
        inverse_rate = getattr(Currency, PURCHASE_RATE_METHOD)(
            company_currency, foreign_currency, company, date
        )
        # El módulo de carga resuelve con COALESCE(..., 1.0), así que "no hay
        # fila de compra para esa fecha" llega indistinguible de "tasa 1.0".
        # Entre dos monedas distintas una tasa de 1.0 no es plausible: se toma
        # como ausencia y se cae al estándar, en vez de valorizar 1 a 1.
        if not inverse_rate or float_is_zero(
            inverse_rate - 1.0, precision_digits=RATE_MATCH_DIGITS
        ):
            return 0.0
        return 1.0 / inverse_rate

    def _uses_purchase_rate(self):
        """
        Indica si la operación debe leerse con la tasa de compra.

        La de venta no se comprueba: el módulo de carga la deja como tasa por
        defecto de Odoo, así que la conversión estándar ya la devuelve.

        Returns:
            bool: True si es compra y el módulo de carga SBS está instalado.
        """
        self.ensure_one()
        _company, company_currency, foreign_currency, _date = self._get_exchange_rate_context()
        return bool(
            company_currency and foreign_currency
            and company_currency != foreign_currency
            and self.exchange_rate_type == RATE_TYPE_PURCHASE
            and hasattr(self.env["res.currency"], PURCHASE_RATE_METHOD)
        )

    def _overrides_odoo_rate(self):
        """
        Indica si la tasa efectiva difiere de la que Odoo aplicaría solo.

        Es la condición que decide si hay que reescribir la valorización
        contable: con tasa forzada, o cuando la operación es de compra y Odoo
        por defecto convertiría a la de venta.

        Returns:
            bool: True si la valorización estándar no sirve.
        """
        self.ensure_one()
        return self._is_forcing_exchange_rate() or self._uses_purchase_rate()

    def _get_effective_exchange_rate(self, market_rates=None):
        """
        Tasa realmente aplicada: la forzada si es utilizable, si no la oficial.

        Args:
            market_rates (dict, optional): memoria para :meth:`_get_market_exchange_rate`.

        Returns:
            float: tasa comercial efectiva.
        """
        self.ensure_one()
        # Se consulta el helper y no un `> 0` pelado: la tasa publicada debe ser
        # la que de verdad se contabiliza, nunca una que el registro no aplica.
        if self._is_forcing_exchange_rate():
            return self.forced_exchange_rate
        return self._get_market_exchange_rate(market_rates)

    def _convert_to_company_currency(self, amount, rate=None):
        """
        Convierte un importe de moneda extranjera a moneda de compañía.

        Centraliza el sentido de la operación: la tasa comercial multiplica.

        Args:
            amount (float): importe en moneda extranjera.
            rate (float, optional): tasa a usar; por defecto la efectiva.

        Returns:
            float: importe en moneda de compañía, ya redondeado.
        """
        self.ensure_one()
        _company, company_currency, _foreign, _date = self._get_exchange_rate_context()
        rate = self._get_effective_exchange_rate() if rate is None else rate
        return (
            company_currency.round(amount * rate) if company_currency else amount * rate
        )

    def _get_inverse_exchange_rate(self):
        """
        Tasa efectiva en convención inversa, la que espera account.move.

        Returns:
            float: 1 / tasa efectiva, o 0.0 si no hay tasa.
        """
        self.ensure_one()
        rate = self._get_effective_exchange_rate()
        return 1.0 / rate if rate > RATE_EPSILON else 0.0

    # -------------------------------------------------------------------------
    # RESTRICCIONES
    # -------------------------------------------------------------------------
    @api.constrains("forced_exchange_rate")
    def _check_forced_exchange_rate(self):
        """
        Rechaza tasas negativas.

        Raises:
            ValidationError: si alguna tasa forzada es negativa.
        """
        for record in self:
            if record.forced_exchange_rate < 0.0:
                raise ValidationError(
                    _("El tipo de cambio forzado no puede ser negativo.")
                )

    # -------------------------------------------------------------------------
    # MÉTODOS COMPUTE
    # -------------------------------------------------------------------------
    @api.depends(
        lambda self: ("forced_exchange_rate", "exchange_rate_type")
        + tuple(self._get_exchange_rate_depends())
    )
    def _compute_exchange_rate(self):
        """
        Publica la tasa efectivamente aplicada.
        """
        # Memoria compartida: los registros con igual (compañía, monedas, fecha,
        # tipo) provocan una sola consulta de tasas.
        market_rates = {}
        for record in self:
            record.exchange_rate = record._get_effective_exchange_rate(market_rates)

    @api.depends(lambda self: tuple(self._get_exchange_rate_type_depends()))
    def _compute_exchange_rate_type(self):
        """
        Propone compra o venta sin pisar la elección manual del usuario.

        El campo es compute+store+readonly=False, así que el ORM lo recalcula
        cada vez que cambia el importe o la fecha. Solo se escribe cuando está
        vacío o cuando la operación deja de admitir tipo.
        """
        for record in self:
            default = record._get_default_exchange_rate_type()
            if not default or not record.exchange_rate_type:
                record.exchange_rate_type = default

    @api.depends(lambda self: tuple(self._get_exchange_rate_depends()))
    def _compute_exchange_rate_case(self):
        """
        Publica la casuística para los modificadores de vista.
        """
        for record in self:
            record.exchange_rate_case = record._get_exchange_rate_case()

    # -------------------------------------------------------------------------
    # MÉTODOS ONCHANGE
    # -------------------------------------------------------------------------
    @api.onchange("forced_exchange_rate")
    def _onchange_forced_exchange_rate(self):
        """
        Limpia la tasa forzada cuando el registro no puede aplicarla.
        """
        for record in self:
            if record.forced_exchange_rate and not record._is_exchange_rate_forceable():
                record.forced_exchange_rate = 0.0
