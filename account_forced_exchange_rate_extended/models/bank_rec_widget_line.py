from odoo import api, fields, models

from .exchange_rate_mixin import CASE_LIQUIDITY, CASE_NONE, EXCHANGE_RATE_TYPES


class BankRecWidgetLine(models.Model):
    """
    Tipo de cambio en el apunte de liquidez del panel de conciliación.

    ``bank.rec.widget.line`` es un modelo en memoria, así que estos campos nunca
    llegan a la base: son solo lo que el contador lee y edita mientras concilia.
    """

    _inherit = "bank.rec.widget.line"

    official_exchange_rate = fields.Float(
        string="Tipo de Cambio",
        digits=0,
        compute="_compute_official_exchange_rate",
        help="""
            Tipo de cambio oficial de la fecha de la transacción, como referencia. \n
            Solo aparece si la transacción está en moneda extranjera; \n
            si está en soles, el tipo de cambio que importa es el de la factura que va a conciliar
        """,
    )

    exchange_rate_currency_name = fields.Char(
        string="Moneda del T.C.",
        compute="_compute_official_exchange_rate",
        help="Moneda a la que corresponde el tipo de cambio mostrado.",
    )

    exchange_rate_type = fields.Selection(
        selection=EXCHANGE_RATE_TYPES,
        string="Tipo de Cambio SBS",
        compute="_compute_exchange_rate_type",
        store=True,
        readonly=False,
        help="""
            Elija si esta operación se valoriza con el tipo de cambio compra o venta. \n
            Al cambiarlo se vuelve a leer el tipo de cambio de la fecha y se recalcula la conciliación.
        """,
    )

    forced_exchange_rate = fields.Float(
        string="Forzar T.C.",
        digits=0,
        compute="_compute_forced_exchange_rate",
        store=True,
        readonly=False,
        help="""
            Digite el tipo de cambio con que quiere cuadrar esta conciliación. \n
            El saldo abierto y la diferencia de cambio se recalculan al instante.\n
            Déjelo vacío para usar el oficial de la fecha.
        """,
    )

    aml_exchange_rate = fields.Float(
        string="T.C. del apunte",
        digits=0,
        compute="_compute_aml_exchange_rate",
        help="""
            Tipo de cambio con que quedó contabilizada esta línea:
            importe en moneda de compañía dividido entre el importe en su moneda.\n
            Permite ver de un vistazo si el apunte y el banco usaron la misma tasa.
        """,
    )

    display_forced_exchange_rate = fields.Boolean(
        string="Muestra el T.C.",
        compute="_compute_display_forced_exchange_rate",
        help="""
            La plantilla del panel lo usa para mostrar u ocultar el bloque de tipo de cambio.
        """,
    )

    # Los @api.depends de este archivo se limitan a ("flag", "wizard_id") a
    # propósito. El modelo no tiene tabla (`_table_query = "0"`), así que una
    # dependencia como `wizard_id.st_line_id.exchange_rate` haría que el ORM
    # emita `SELECT ... FROM (0)` al escribir cualquier línea de extracto y
    # rompería su creación. Es la misma precaución que toma Odoo en sus campos
    # related; los valores se refrescan porque `_action_reload_liquidity_line`
    # reconstruye `line_ids` entero.
    @api.depends("flag", "wizard_id")
    def _compute_forced_exchange_rate(self):
        """
        Trae al panel la tasa forzada de la transacción.
        """
        for line in self:
            st_line = line.wizard_id.st_line_id
            line.forced_exchange_rate = (
                st_line.forced_exchange_rate if line.flag == "liquidity" else 0.0
            )

    @api.depends("flag", "wizard_id")
    def _compute_exchange_rate_type(self):
        """
        Trae al panel el tipo de cambio SBS elegido en la transacción.
        """
        for line in self:
            st_line = line.wizard_id.st_line_id
            line.exchange_rate_type = (
                st_line.exchange_rate_type if line.flag == "liquidity" else False
            )

    @api.depends("flag", "wizard_id")
    def _compute_official_exchange_rate(self):
        """
        Publica el tipo de cambio de la fecha y su moneda, como referencia.
        """
        for line in self:
            st_line = line.wizard_id.st_line_id
            shows_rate = (
                line.flag == "liquidity"
                and st_line
                and st_line._get_exchange_rate_case() == CASE_LIQUIDITY
            )
            if shows_rate:
                line.official_exchange_rate = st_line._get_market_exchange_rate()
                line.exchange_rate_currency_name = st_line.currency_id.name
            else:
                # Una transacción en moneda de compañía no tiene tasa propia: la
                # relevante es la de la contrapartida, desconocida hasta montarla.
                line.official_exchange_rate = 0.0
                line.exchange_rate_currency_name = False

    @api.depends("balance", "amount_currency", "currency_id")
    def _compute_aml_exchange_rate(self):
        """
        Tipo de cambio implícito de cada línea del asiento.
        """
        for line in self:
            converts = (
                line.currency_id
                and line.currency_id != line.company_currency_id
                and line.amount_currency
            )
            line.aml_exchange_rate = (
                abs(line.balance / line.amount_currency) if converts else 0.0
            )

    @api.depends("flag", "wizard_id")
    def _compute_display_forced_exchange_rate(self):
        """
        Decide si el bloque de tipo de cambio se muestra en el panel.
        """
        for line in self:
            st_line = line.wizard_id.st_line_id
            line.display_forced_exchange_rate = bool(
                line.flag == "liquidity"
                and st_line
                and st_line._get_exchange_rate_case() != CASE_NONE
            )
