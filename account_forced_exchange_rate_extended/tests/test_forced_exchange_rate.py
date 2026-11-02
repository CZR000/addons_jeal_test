from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account_accountant.tests.test_bank_rec_widget_common import (
    TestBankRecWidgetCommon,
)
from odoo.addons.account_forced_exchange_rate_extended.models.exchange_rate_mixin import (
    PURCHASE_RATE_METHOD,
    RATE_DIGITS,
)


class TestForcedExchangeRateCommon(TestBankRecWidgetCommon):
    """
    Escenario base: compañía en USD, moneda extranjera EUR.

    ``setup_other_currency('EUR')`` registra una tasa de 2.0 EUR por 1 USD desde
    2017-01-01, así que el tipo de cambio comercial oficial es 0.50 USD por EUR.
    Las pruebas fuerzan 0.40 para producir una diferencia de cambio determinista.
    """

    @classmethod
    def setup_independent_company(cls, **kwargs):
        group = cls.env.ref('restrict_journal_creation.group_allow_create_account_journal', raise_if_not_found=False)
        if group:
            cls.env.user.write({'groups_id': [(4, group.id)]})
        return super().setup_independent_company(**kwargs)

    OFFICIAL_RATE = 0.5
    FORCED_RATE = 0.4

    @classmethod
    def setUpClass(cls):
        """
        Compañía en USD, diario en EUR y tasas oficiales de la clase.
        """
        super().setUpClass()
        cls.company_currency = cls.company_data["company"].currency_id
        cls.foreign_journal = cls.env["account.journal"].create(
            {
                "name": "Bank EUR",
                "code": "BNKEU",
                "type": "bank",
                "currency_id": cls.other_currency.id,
            }
        )

    def _create_foreign_st_line(self, **kwargs):
        """
        Transacción en el diario en moneda extranjera (caso `liquidity`).
        """
        return self._create_st_line(100.0, journal_id=self.foreign_journal.id, **kwargs)

    def _create_invoice_in_foreign_currency(self, currency=None, price_unit=100.0):
        """
        Crea una factura de cliente en moneda extranjera.

        Args:
            currency (recordset, optional): moneda de la factura.
            price_unit (float, optional): importe de la única línea.

        Returns:
            recordset: el ``account.move.line`` por cobrar, ya contabilizado.
        """
        return self._create_invoice_line(
            "out_invoice",
            currency_id=(currency or self.other_currency).id,
            invoice_line_ids=[{"price_unit": price_unit}],
        )

    def _mount(self, st_line, aml=None):
        """
        Monta una transacción en un widget de conciliación nuevo.

        Args:
            st_line (recordset): transacción bancaria a conciliar.
            aml (recordset, optional): apunte a montar como contrapartida.

        Returns:
            recordset: ``bank.rec.widget`` en memoria con la transacción montada.
        """
        wizard = (
            self.env["bank.rec.widget"]
            .with_context(default_st_line_id=st_line.id)
            .new({})
        )
        if aml is not None:
            wizard._action_add_new_amls(aml)
        return wizard


@tagged("post_install", "-at_install")
class TestExchangeRateCase(TestForcedExchangeRateCommon):
    """
    Clasificación de la casuística: qué transacción admite forzar y dónde.
    """

    def test_case_liquidity_foreign_journal(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)

        self.assertEqual(st_line.exchange_rate_case, "liquidity")
        self.assertTrue(st_line._is_exchange_rate_forceable())
        self.assertTrue(st_line._forces_liquidity_valuation())
        self.assertFalse(st_line._forces_counterpart_valuation())

    def test_case_counterpart_company_currency_journal(self):
        st_line = self._create_st_line(100.0, forced_exchange_rate=self.FORCED_RATE)

        self.assertEqual(st_line.exchange_rate_case, "counterpart")
        self.assertTrue(st_line._is_exchange_rate_forceable())
        self.assertFalse(st_line._forces_liquidity_valuation())
        self.assertTrue(st_line._forces_counterpart_valuation())

    def test_case_none_with_a_third_currency(self):
        """
        Una tercera moneda define la tasa: forzarla descuadraría el asiento.
        """
        st_line = self._create_foreign_st_line(
            foreign_currency_id=self.other_currency_2.id,
            amount_currency=300.0,
            forced_exchange_rate=self.FORCED_RATE,
        )

        self.assertEqual(st_line.exchange_rate_case, "none")
        self.assertFalse(st_line._is_exchange_rate_forceable())
        self.assertFalse(st_line._is_forcing_exchange_rate())
        self.assertEqual(st_line.exchange_rate, self.OFFICIAL_RATE)
        self.assertEqual(st_line.move_id.to_force_exchange_rate, 0.0)
        self.assertEqual(sum(st_line.move_id.line_ids.mapped("balance")), 0.0)

    def test_case_none_when_the_bank_gives_the_company_amount(self):
        st_line = self._create_foreign_st_line(
            foreign_currency_id=self.company_currency.id,
            amount_currency=50.0,
        )

        self.assertEqual(st_line.exchange_rate_case, "none")
        self.assertFalse(st_line._is_exchange_rate_forceable())


@tagged("post_install", "-at_install")
class TestExchangeRateResolution(TestForcedExchangeRateCommon):
    """
    Resolución de la tasa: oficial, forzada y su convención inversa.
    """

    def test_falls_back_to_the_official_rate(self):
        st_line = self._create_foreign_st_line()

        self.assertEqual(st_line.exchange_rate, self.OFFICIAL_RATE)
        self.assertEqual(st_line._get_market_exchange_rate(), self.OFFICIAL_RATE)
        self.assertFalse(st_line._is_forcing_exchange_rate())

    def test_uses_the_forced_rate(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)

        self.assertEqual(st_line.exchange_rate, self.FORCED_RATE)
        # El oficial se sigue publicando como referencia, sin contaminarse.
        self.assertEqual(st_line._get_market_exchange_rate(), self.OFFICIAL_RATE)

    def test_rate_follows_the_date(self):
        """
        `setup_other_currency` deja 3.0 EUR por USD antes de 2017.
        """
        st_line = self._create_foreign_st_line(date="2016-06-01")

        self.assertAlmostEqual(st_line.exchange_rate, 1 / 3.0)

        st_line.date = "2019-01-01"

        self.assertEqual(st_line.exchange_rate, self.OFFICIAL_RATE)

    def test_forced_rate_ignores_the_date(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)

        st_line.date = "2016-06-01"

        self.assertEqual(st_line.exchange_rate, self.FORCED_RATE)

    def test_clearing_the_rate_restores_the_official_one(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)

        st_line.forced_exchange_rate = 0.0

        self.assertEqual(st_line.exchange_rate, self.OFFICIAL_RATE)

    def test_inverse_rate_convention(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)

        self.assertAlmostEqual(
            st_line._get_inverse_exchange_rate(), 1 / self.FORCED_RATE
        )

    def test_conversion_helper(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)

        self.assertEqual(st_line._convert_to_company_currency(100.0), 40.0)
        self.assertEqual(st_line._convert_to_company_currency(100.0, rate=0.6), 60.0)

    def test_negative_rate_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_foreign_st_line(forced_exchange_rate=-1.0)

    def test_rounding_residue_is_not_a_rate(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=1e-15)

        self.assertFalse(st_line._is_forcing_exchange_rate())
        self.assertEqual(st_line.exchange_rate, self.OFFICIAL_RATE)


@tagged("post_install", "-at_install")
class TestLiquidityValuation(TestForcedExchangeRateCommon):
    """
    Caso `liquidity`: la tasa valoriza la propia transacción bancaria.
    """

    def test_forced_rate_drives_the_liquidity_balance(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)
        liquidity_line, suspense_line, _other_lines = st_line._seek_for_lines()

        self.assertRecordValues(
            liquidity_line, [{"amount_currency": 100.0, "balance": 40.0}]
        )
        self.assertRecordValues(
            suspense_line, [{"amount_currency": -100.0, "balance": -40.0}]
        )

    def test_changing_the_rate_resynchronizes_the_entry(self):
        st_line = self._create_foreign_st_line()
        self.assertEqual(st_line._seek_for_lines()[0].balance, 50.0)

        st_line.forced_exchange_rate = self.FORCED_RATE

        self.assertEqual(st_line._seek_for_lines()[0].balance, 40.0)

    def test_outbound_transaction_keeps_its_sign(self):
        st_line = self._create_st_line(
            -100.0,
            journal_id=self.foreign_journal.id,
            forced_exchange_rate=self.FORCED_RATE,
        )
        liquidity_line, suspense_line, _other = st_line._seek_for_lines()

        self.assertRecordValues(
            liquidity_line, [{"amount_currency": -100.0, "balance": -40.0}]
        )
        self.assertRecordValues(
            suspense_line, [{"amount_currency": 100.0, "balance": 40.0}]
        )

    def test_company_currency_transaction_never_revalues_the_bank_leg(self):
        st_line = self._create_st_line(100.0, forced_exchange_rate=self.FORCED_RATE)

        self.assertRecordValues(
            st_line._seek_for_lines()[0], [{"amount_currency": 100.0, "balance": 100.0}]
        )

    def test_undoing_the_reconciliation_keeps_the_rate(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)
        self._mount(
            st_line, self._create_invoice_in_foreign_currency()
        )._action_validate()
        self.assertTrue(st_line.is_reconciled)

        st_line.action_undo_reconciliation()

        self.assertFalse(st_line.is_reconciled)
        self.assertEqual(st_line._seek_for_lines()[0].balance, 40.0)


@tagged("post_install", "-at_install")
class TestMoveSynchronization(TestForcedExchangeRateCommon):
    """
    Espejo de la tasa en el asiento, en la convención inversa.
    """

    def test_forced_rate_is_mirrored_as_its_inverse(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE, exchange_rate_type="sale")

        self.assertAlmostEqual(
            st_line.move_id.to_force_exchange_rate, 1 / self.FORCED_RATE
        )

        st_line.forced_exchange_rate = 0.0

        self.assertEqual(st_line.move_id.to_force_exchange_rate, 0.0)

    def test_counterpart_case_is_mirrored_too(self):
        """
        Necesario para que el asiento cuadre tras conciliar en soles.
        """
        st_line = self._create_st_line(100.0, forced_exchange_rate=self.FORCED_RATE)

        self.assertAlmostEqual(
            st_line.move_id.to_force_exchange_rate, 1 / self.FORCED_RATE
        )

    def test_sync_is_batched_by_rate(self):
        st_lines = self.env["account.bank.statement.line"]
        for rate in (self.FORCED_RATE, self.FORCED_RATE, 0.45):
            st_lines |= self._create_foreign_st_line(forced_exchange_rate=rate)

        # `to_force_exchange_rate` se almacena con 12 decimales, así que
        # 1/0.45 = 2.2222222222222223 llega redondeado. Comparación por
        # aproximación, no exacta.
        for stored, expected in zip(
            st_lines.move_id.mapped("to_force_exchange_rate"),
            [1 / self.FORCED_RATE, 1 / self.FORCED_RATE, 1 / 0.45],
        ):
            self.assertAlmostEqual(stored, expected, places=RATE_DIGITS - 1)

    def test_creating_without_a_rate_clears_the_move(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=0.0, exchange_rate_type="sale")

        self.assertEqual(st_line.move_id.to_force_exchange_rate, 0.0)
        self.assertEqual(st_line.exchange_rate, self.OFFICIAL_RATE)

    def test_writing_the_same_rate_is_a_no_op(self):
        """
        Sin cambio real no debe reconstruirse el asiento.

        `_synchronize_to_moves` elimina las contrapartidas al reconstruir, así
        que una escritura sin cambio en una transacción conciliada deshacía la
        conciliación en silencio.
        """
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)
        move = st_line.move_id
        before = move.write_date

        st_line.write({"forced_exchange_rate": self.FORCED_RATE})

        self.assertFalse(
            self.env["account.bank.statement.line"]
            .browse(st_line.id)
            ._forced_rate_differs(self.FORCED_RATE)
        )
        self.assertEqual(move.write_date, before)

    def test_same_rate_on_a_reconciled_line_keeps_the_reconciliation(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)
        self._mount(
            st_line, self._create_invoice_in_foreign_currency()
        )._action_validate()
        self.assertTrue(st_line.is_reconciled)

        st_line.write({"forced_exchange_rate": self.FORCED_RATE})

        self.assertTrue(st_line.is_reconciled)

    def test_rate_cannot_be_changed_once_reconciled(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)
        self._mount(
            st_line, self._create_invoice_in_foreign_currency()
        )._action_validate()
        self.assertTrue(st_line.is_reconciled)

        with self.assertRaises(UserError):
            st_line.forced_exchange_rate = 0.45

        # Reescribir exactamente la misma tasa no es un cambio y debe permitirse.
        st_line.forced_exchange_rate = self.FORCED_RATE


@tagged("post_install", "-at_install")
class TestCounterpartValuation(TestForcedExchangeRateCommon):
    """
    Caso `counterpart`: cobro en moneda de la compañía de una factura en ME.
    """

    def _mount_company_currency_widget(self, forced_rate=0.0, amount=50.0):
        """
        Cobro de 50 USD que paga una factura de 100 EUR.

        La factura se contabiliza al oficial 0.50, así que a esa tasa la
        conciliación es exacta y no aparece diferencia de cambio.
        """
        st_line = self._create_st_line(amount, forced_exchange_rate=forced_rate)
        return st_line, self._mount(st_line, self._create_invoice_in_foreign_currency())

    def test_official_rate_gives_no_difference(self):
        _st_line, wizard = self._mount_company_currency_widget()

        self.assertFalse(
            wizard.line_ids.filtered(lambda line: line.flag == "exchange_diff")
        )

    def test_forced_rate_drives_the_difference(self):
        _st_line, wizard = self._mount_company_currency_widget(
            forced_rate=self.FORCED_RATE
        )

        # Factura contabilizada a 0.50 (50 USD), cobrada a 0.40 (40 USD).
        self.assertRecordValues(
            wizard.line_ids.filtered(lambda line: line.flag == "exchange_diff"),
            [{"balance": 10.0}],
        )

    def test_editing_the_rate_keeps_the_mounted_journal_items(self):
        """
        Reconstruir el widget aquí descartaría el trabajo del contador.
        """
        st_line, wizard = self._mount_company_currency_widget()
        liquidity_line = wizard.line_ids.filtered(lambda line: line.flag == "liquidity")
        mounted_amls = wizard.line_ids.filtered(
            lambda line: line.flag == "new_aml"
        ).source_aml_id
        self.assertTrue(mounted_amls)

        liquidity_line.forced_exchange_rate = self.FORCED_RATE
        wizard._js_action_line_changed(liquidity_line.index, "forced_exchange_rate")

        self.assertEqual(st_line.forced_exchange_rate, self.FORCED_RATE)
        self.assertEqual(
            wizard.line_ids.filtered(lambda line: line.flag == "new_aml").source_aml_id,
            mounted_amls,
        )
        self.assertRecordValues(
            wizard.line_ids.filtered(lambda line: line.flag == "exchange_diff"),
            [{"balance": 10.0}],
        )

    def test_validating_closes_the_reconciliation_at_the_forced_rate(self):
        st_line, wizard = self._mount_company_currency_widget(
            forced_rate=self.FORCED_RATE, amount=100.0 * self.FORCED_RATE
        )

        wizard._action_validate()

        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(sum(st_line.move_id.line_ids.mapped("balance")), 0.0)

    def test_two_foreign_currencies_under_one_rate_are_refused(self):
        st_line, wizard = self._mount_company_currency_widget(
            forced_rate=self.FORCED_RATE
        )
        wizard._action_add_new_amls(
            self._create_invoice_in_foreign_currency(currency=self.other_currency_2)
        )

        with self.assertRaises(UserError):
            wizard._action_validate()

        # Sin tasa forzada, Odoo gestiona la mezcla por su cuenta.
        amls = wizard.line_ids.filtered(lambda line: line.flag == 'new_aml').source_aml_id
        st_line.write({'forced_exchange_rate': 0.0, 'amount': sum(amls.mapped('amount_residual'))})
        wizard = self._mount(st_line, amls)
        wizard._action_validate()
        self.assertTrue(st_line.is_reconciled)

    def test_reconcile_mixin_refuses_two_currencies(self):
        """
        El mixin de conciliación valida sin depender del widget.
        """
        _st_line, wizard = self._mount_company_currency_widget(
            forced_rate=self.FORCED_RATE
        )
        currencies = self.other_currency | self.other_currency_2

        with self.assertRaises(UserError):
            wizard._check_forced_rate_covers_a_single_currency(currencies)

        # Una sola moneda extranjera no dispara nada.
        wizard._check_forced_rate_covers_a_single_currency(self.other_currency)

    def test_reconcile_mixin_requires_exchange_accounts(self):
        """
        Sin cuentas de diferencia de cambio el error es explícito.
        """
        _st_line, wizard = self._mount_company_currency_widget(
            forced_rate=self.FORCED_RATE
        )
        company = wizard.company_id
        company.expense_currency_exchange_account_id = False
        company.income_currency_exchange_account_id = False

        with self.assertRaises(UserError):
            wizard._prepare_forced_exchange_diff(-50.0, -100.0, company)


@tagged("post_install", "-at_install")
class TestWidgetFields(TestForcedExchangeRateCommon):
    """
    Lo que el contador ve en el panel de operaciones manuales.
    """

    def test_foreign_transaction_shows_both_rates(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)
        liquidity_line = self._mount(st_line).line_ids.filtered(
            lambda x: x.flag == "liquidity"
        )

        self.assertTrue(liquidity_line.display_forced_exchange_rate)
        self.assertEqual(liquidity_line.official_exchange_rate, self.OFFICIAL_RATE)
        self.assertEqual(
            liquidity_line.exchange_rate_currency_name, self.other_currency.name
        )
        self.assertEqual(liquidity_line.forced_exchange_rate, self.FORCED_RATE)

    def test_company_currency_transaction_shows_only_the_override(self):
        st_line = self._create_st_line(100.0)
        liquidity_line = self._mount(st_line).line_ids.filtered(
            lambda x: x.flag == "liquidity"
        )

        self.assertTrue(liquidity_line.display_forced_exchange_rate)
        self.assertEqual(liquidity_line.official_exchange_rate, 0.0)
        self.assertFalse(liquidity_line.exchange_rate_currency_name)

    def test_third_currency_transaction_hides_everything(self):
        st_line = self._create_foreign_st_line(
            foreign_currency_id=self.other_currency_2.id, amount_currency=300.0
        )
        liquidity_line = self._mount(st_line).line_ids.filtered(
            lambda x: x.flag == "liquidity"
        )

        self.assertFalse(liquidity_line.display_forced_exchange_rate)

    def test_rate_is_hidden_on_non_liquidity_lines(self):
        st_line = self._create_foreign_st_line()
        wizard = self._mount(st_line, self._create_invoice_in_foreign_currency())

        other_lines = wizard.line_ids.filtered(lambda line: line.flag != "liquidity")

        self.assertTrue(other_lines)
        self.assertFalse(any(other_lines.mapped("display_forced_exchange_rate")))

    def test_editing_a_foreign_transaction_rebuilds_the_entry(self):
        st_line = self._create_foreign_st_line()
        wizard = self._mount(st_line)
        liquidity_line = wizard.line_ids.filtered(lambda line: line.flag == "liquidity")

        liquidity_line.forced_exchange_rate = self.FORCED_RATE
        wizard._js_action_line_changed(liquidity_line.index, "forced_exchange_rate")

        self.assertEqual(st_line.forced_exchange_rate, self.FORCED_RATE)
        self.assertEqual(st_line.exchange_rate, self.FORCED_RATE)
        self.assertEqual(
            wizard.line_ids.filtered(lambda line: line.flag == "liquidity").balance,
            40.0,
        )

    def test_clearing_the_rate_from_the_widget(self):
        st_line = self._create_foreign_st_line(forced_exchange_rate=self.FORCED_RATE)
        wizard = self._mount(st_line)
        liquidity_line = wizard.line_ids.filtered(lambda line: line.flag == "liquidity")

        liquidity_line.forced_exchange_rate = 0.0
        wizard._js_action_line_changed(liquidity_line.index, "forced_exchange_rate")

        self.assertEqual(st_line.forced_exchange_rate, 0.0)
        self.assertEqual(st_line.exchange_rate, self.OFFICIAL_RATE)


@tagged("post_install", "-at_install")
class TestExchangeRateType(TestForcedExchangeRateCommon):
    """Selección compra/venta y su lectura desde res.currency.rate."""

    def test_default_is_purchase_for_inbound(self):
        st_line = self._create_foreign_st_line()

        self.assertEqual(st_line.exchange_rate_type, "purchase")

    def test_default_is_sale_for_outbound(self):
        st_line = self._create_st_line(-100.0, journal_id=self.foreign_journal.id)

        self.assertEqual(st_line.exchange_rate_type, "sale")

    def test_no_type_without_conversion(self):
        st_line = self._create_foreign_st_line(
            foreign_currency_id=self.other_currency_2.id,
            amount_currency=300.0,
        )

        self.assertFalse(st_line.exchange_rate_type)

    def test_user_choice_overrides_the_default(self):
        st_line = self._create_foreign_st_line()

        st_line.exchange_rate_type = "sale"

        self.assertEqual(st_line.exchange_rate_type, "sale")

    def test_falls_back_while_the_sbs_module_is_missing(self):
        """Sin el método de compra en res.currency se usa lo estándar."""
        if hasattr(self.env["res.currency"], PURCHASE_RATE_METHOD):
            self.skipTest("El módulo de carga de tasas SBS ya está instalado.")

        st_line = self._create_foreign_st_line()

        self.assertEqual(
            st_line._get_typed_market_exchange_rate(
                self.other_currency, st_line.company_id, st_line.date
            ),
            0.0,
        )
        self.assertEqual(st_line.exchange_rate, self.OFFICIAL_RATE)
        # Sin el módulo SBS la valorización es la estándar de Odoo.
        self.assertFalse(st_line._uses_purchase_rate())
        self.assertFalse(st_line._overrides_odoo_rate())

    def test_purchase_overrides_the_valuation_when_sbs_is_installed(self):
        """Elegir compra debe revalorizar el asiento, no solo la pantalla."""
        st_line = self._create_foreign_st_line()
        self.assertEqual(st_line.exchange_rate_type, "purchase")

        # Se simula el módulo SBS: la venta es la tasa estándar y la compra
        # llega por su método propio.
        Currency = type(self.env["res.currency"])
        setattr(Currency, PURCHASE_RATE_METHOD,
                lambda self, from_currency, to_currency, company, date: 2.5)
        self.addCleanup(delattr, Currency, PURCHASE_RATE_METHOD)

        st_line.invalidate_recordset(["exchange_rate"])

        self.assertTrue(st_line._uses_purchase_rate())
        self.assertTrue(st_line._overrides_odoo_rate())
        self.assertTrue(st_line._forces_liquidity_valuation())
        # 1 / 2.5 = 0.40 unidades de compañía por unidad extranjera.
        self.assertAlmostEqual(st_line._get_market_exchange_rate(), 0.4)

    def test_missing_purchase_rate_falls_back_to_standard(self):
        """El módulo de carga devuelve 1.0 cuando no hay fila de compra.

        Sin esta comprobación, un ingreso en dólares se valorizaría 1 a 1.
        """
        st_line = self._create_foreign_st_line()
        st_line.exchange_rate_type = "purchase"

        Currency = type(self.env["res.currency"])
        setattr(Currency, PURCHASE_RATE_METHOD,
                lambda self, from_currency, to_currency, company, date: 1.0)
        self.addCleanup(delattr, Currency, PURCHASE_RATE_METHOD)

        self.assertEqual(
            st_line._get_typed_market_exchange_rate(
                self.other_currency, st_line.company_id, st_line.date
            ),
            0.0,
        )
        st_line.invalidate_recordset(["exchange_rate"])
        self.assertEqual(st_line.exchange_rate, self.OFFICIAL_RATE)

    def test_manual_choice_survives_an_amount_change(self):
        """El ORM recalcula el campo al cambiar el importe: no debe pisarlo."""
        st_line = self._create_foreign_st_line()
        self.assertEqual(st_line.exchange_rate_type, "purchase")

        st_line.exchange_rate_type = "sale"
        st_line.amount = 120.0

        self.assertEqual(st_line.exchange_rate_type, "sale")

    def test_type_cannot_be_changed_once_reconciled(self):
        st_line = self._create_foreign_st_line()
        self._mount(st_line, self._create_invoice_in_foreign_currency())._action_validate()
        self.assertTrue(st_line.is_reconciled)

        with self.assertRaises(UserError):
            st_line.exchange_rate_type = "sale"

    def test_widget_exposes_the_selection(self):
        st_line = self._create_foreign_st_line()
        wizard = self._mount(st_line)
        liquidity_line = wizard.line_ids.filtered(lambda line: line.flag == "liquidity")

        self.assertEqual(liquidity_line.exchange_rate_type, "purchase")

        liquidity_line.exchange_rate_type = "sale"
        wizard._js_action_line_changed(liquidity_line.index, "exchange_rate_type")

        self.assertEqual(st_line.exchange_rate_type, "sale")


@tagged("post_install", "-at_install")
class TestRoundingGap(TestForcedExchangeRateCommon):
    """El desfase de redondeo de la factura se asienta como diferencia de cambio.

    La pata bancaria conserva ``importe x tasa`` —lo que da la calculadora— y los
    céntimos que la factura trae de más van a la cuenta de diferencia de cambio.
    """

    def _invoice_with_rounding_gap(self):
        """Factura cuyas líneas redondeadas no suman la conversión del total.

        Dos líneas de 33.33 EUR a 0.50 dan 16.67 + 16.67 = 33.34 USD, mientras
        que 66.66 x 0.50 = 33.33. Un céntimo de desfase, el mismo mecanismo del
        caso real.

        Returns:
            recordset: el ``account.move.line`` por cobrar.
        """
        return self._create_invoice_line(
            "out_invoice",
            currency_id=self.other_currency.id,
            invoice_line_ids=[{"price_unit": 33.33}, {"price_unit": 33.33}],
        )

    def test_bank_leg_keeps_amount_times_rate(self):
        aml = self._invoice_with_rounding_gap()
        st_line = self._create_st_line(
            abs(aml.amount_currency), journal_id=self.foreign_journal.id)
        wizard = self._mount(st_line, aml)

        # 66.66 x 0.50 = 33.33, el número de la calculadora. La factura quedó en
        # 33.34 porque convirtió y redondeó línea a línea.
        self.assertRecordValues(
            wizard.line_ids.filtered(lambda x: x.flag == "liquidity"),
            [{"balance": 33.33}],
        )
        self.assertRecordValues(
            wizard.line_ids.filtered(lambda x: x.flag == "exchange_diff"),
            [{"balance": 0.01}],
        )
        # Esos céntimos cierran el asiento: no quedan como saldo abierto.
        self.assertFalse(wizard.line_ids.filtered(lambda x: x.flag == "auto_balance"))
        self.assertEqual(wizard.state, "valid")
        self.assertEqual(sum(wizard.line_ids.mapped("balance")), 0.0)

    def test_real_exchange_difference_is_untouched(self):
        """Una diferencia de cambio de verdad se asienta igual que antes."""
        aml = self._create_invoice_in_foreign_currency()
        st_line = self._create_st_line(
            100.0, journal_id=self.foreign_journal.id,
            forced_exchange_rate=self.FORCED_RATE)
        wizard = self._mount(st_line, aml)

        exchange_diff = wizard.line_ids.filtered(lambda x: x.flag == "exchange_diff")

        self.assertRecordValues(exchange_diff, [{"balance": 10.0}])

    def test_forced_counterpart_difference_is_the_forced_one(self):
        """En el caso `counterpart` la diferencia sale de la tasa forzada."""
        aml = self._create_invoice_in_foreign_currency()
        st_line = self._create_st_line(100.0 * self.FORCED_RATE, forced_exchange_rate=self.FORCED_RATE)
        self.assertEqual(st_line.exchange_rate_case, "counterpart")

        wizard = self._mount(st_line, aml)

        self.assertRecordValues(
            wizard.line_ids.filtered(lambda x: x.flag == "exchange_diff"),
            [{"balance": 10.0}],
        )
        self.assertFalse(wizard.line_ids.filtered(lambda x: x.flag == "auto_balance"))

    def test_validating_closes_the_invoice(self):
        aml = self._invoice_with_rounding_gap()
        st_line = self._create_st_line(
            abs(aml.amount_currency), journal_id=self.foreign_journal.id)

        self._mount(st_line, aml)._action_validate()

        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(sum(st_line.move_id.line_ids.mapped("balance")), 0.0)
        # La factura queda saldada pese al céntimo de desfase.
        self.assertEqual(aml.amount_residual, 0.0)

        liquidity_line, _suspense, _other = st_line._seek_for_lines()
        self.assertEqual(liquidity_line.amount_currency, st_line.amount)
        self.assertEqual(liquidity_line.balance, 33.33)


@tagged("post_install", "-at_install")
class TestPurchaseRateWithoutForeignCurrency(TestForcedExchangeRateCommon):
    def test_company_currency_does_not_force_a_one_to_one_rate(self):
        st_line = self._create_st_line(50.0)
        self.assertFalse(st_line._uses_purchase_rate())
        self.assertEqual(st_line.move_id.to_force_exchange_rate, 0.0)
        wizard = self._mount(st_line, self._create_invoice_in_foreign_currency())
        self.assertFalse(wizard.line_ids.filtered(lambda line: line.flag in ('exchange_diff', 'auto_balance')))
        wizard._action_validate()
        self.assertTrue(st_line.is_reconciled)
