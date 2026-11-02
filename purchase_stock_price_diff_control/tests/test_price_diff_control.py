from unittest.mock import patch
from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged, TransactionCase

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestPriceDiffControl(AccountTestInvoicingCommon):
    @classmethod
    def setup_independent_company(cls, **kwargs):
        # A chart creates journals; respect optional customer access restrictions.
        group = cls.env.ref('restrict_journal_creation.group_allow_create_account_journal', raise_if_not_found=False)
        if group:
            cls.env.user.write({'groups_id': [(4, group.id)]})
        return super().setup_independent_company(**kwargs)

    """El costo no debe inflarse al re-publicar una factura de proveedor.

    Reproduce el caso reportado: recepción a 612.50 y factura a 7248.08; cada
    ciclo borrador/publicar volvía a sumar la diferencia de 6635.58.
    """

    RECEIPT_PRICE = 612.50
    BILL_PRICE = 7248.08
    DIFF = 6635.58

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.env.user.company_ids |= cls.company
        cls.warehouse = cls.env['stock.warehouse'].sudo().create({
            'name': 'Price difference test warehouse', 'code': 'PDIF',
            'company_id': cls.company.id,
        })
        cls.categ = cls.env["product.category"].create(
            {
                "name": "Mercadería AVCO",
                "property_cost_method": "average",
                "property_valuation": "real_time",
                "property_stock_valuation_account_id": cls.company_data['default_account_assets'].id,
                "property_stock_account_input_categ_id": cls.company_data['default_account_expense'].id,
                "property_stock_account_output_categ_id": cls.company_data['default_account_expense'].id,
                "property_stock_journal": cls.company_data['default_journal_misc'].id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Variador de frecuencia (test)",
                "is_storable": True,
                "type": "consu",
                "categ_id": cls.categ.id,
                "standard_price": 0.0,
                "purchase_ok": True,
            }
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Proveedor test"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _receive(self, qty=1.0, price=None):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": qty,
                            "price_unit": self.RECEIPT_PRICE if price is None else price,
                            "name": self.product.name,
                            "date_planned": fields.Datetime.now(),
                        }
                    )
                ],
            }
        )
        po.button_confirm()
        picking = po.picking_ids
        picking.move_ids.write({"quantity": qty, "picked": True})
        picking.button_validate()
        return po

    def _bill(self, po, price):
        po.action_create_invoice()
        bill = po.invoice_ids
        bill.invoice_date = fields.Date.context_today(bill)
        bill.invoice_line_ids.filtered(
            lambda line: line.product_id == self.product
        ).price_unit = price
        bill.action_post()
        return bill

    @property
    def _layers(self):
        return self.env["stock.valuation.layer"].search(
            [("product_id", "=", self.product.id)], order="id"
        )

    def _total_value(self):
        return sum(self._layers.mapped("value"))

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_01_single_post_still_adjusts(self):
        """Una sola publicación sigue ajustando el costo como hace el core."""
        po = self._receive()
        self.assertAlmostEqual(self._total_value(), self.RECEIPT_PRICE, places=2)

        self._bill(po, self.BILL_PRICE)
        self.assertAlmostEqual(self._total_value(), self.BILL_PRICE, places=2)
        self.assertAlmostEqual(self.product.standard_price, self.BILL_PRICE, places=2)

    def test_02_repost_does_not_accumulate(self):
        """El bug reportado: re-publicar no debe volver a sumar la diferencia."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)

        for _iteration in range(3):
            bill.button_draft()
            bill.action_post()
            self.assertAlmostEqual(
                self._total_value(),
                self.BILL_PRICE,
                places=2,
                msg="El valor se acumuló al re-publicar la factura",
            )
            self.assertAlmostEqual(self.product.standard_price, self.BILL_PRICE, places=2)

        # Sin el arreglo el total sería 612.50 + 4 * 6635.58 = 27154.82
        self.assertAlmostEqual(self._total_value(), self.BILL_PRICE, places=2)

    def test_03_repost_with_new_price_uses_last_value(self):
        """Si cambian el precio antes de re-publicar, manda el último valor."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)

        new_price = 5000.0
        bill.button_draft()
        bill.invoice_line_ids.filtered(
            lambda line: line.product_id == self.product
        ).price_unit = new_price
        bill.action_post()

        self.assertAlmostEqual(self._total_value(), new_price, places=2)
        self.assertAlmostEqual(self.product.standard_price, new_price, places=2)

    def test_04_draft_removes_adjustment(self):
        """Una factura en borrador no debe seguir valorizando el inventario."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)

        bill.button_draft()
        self.assertAlmostEqual(self._total_value(), self.RECEIPT_PRICE, places=2)
        self.assertAlmostEqual(self.product.standard_price, self.RECEIPT_PRICE, places=2)

    def test_05_reversal_layers_are_balanced(self):
        """Cada reversión compensa exactamente el ajuste que anula."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)
        bill.button_draft()
        bill.action_post()

        reversals = self._layers.filtered("pdiff_reversal_of_id")
        self.assertTrue(reversals, "No se generó la capa de reversión")
        for reversal in reversals:
            self.assertAlmostEqual(
                reversal.value, -reversal.pdiff_reversal_of_id.value, places=2
            )
            self.assertTrue(
                reversal.account_move_id,
                "La reversión debe generar su asiento contable",
            )
        # La capa de origen vuelve a reflejar sólo el ajuste vigente.
        origin = self._layers.filtered(lambda layer: not layer.stock_valuation_layer_id)
        self.assertAlmostEqual(origin.remaining_value, self.BILL_PRICE, places=2)

    def test_06_idempotent_reversal(self):
        """Revertir dos veces el mismo ajuste no duplica la corrección."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)
        adjustments = self._layers.filtered("pdiff_is_adjustment")

        first = adjustments._pdiff_reverse_adjustments()
        second = adjustments._pdiff_reverse_adjustments()
        self.assertTrue(first)
        self.assertFalse(second, "Un ajuste ya revertido no debe revertirse otra vez")
        self.assertAlmostEqual(self._total_value(), self.RECEIPT_PRICE, places=2)

    def test_07_cleanup_wizard_detects_and_fixes(self):
        """El asistente detecta y corrige duplicados preexistentes."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)

        # Simular el histórico: duplicar el ajuste como lo hacía el core.
        adjustment = self._layers.filtered("pdiff_is_adjustment")
        self.assertEqual(len(adjustment), 1)
        origin = adjustment.stock_valuation_layer_id
        clones = self.env["stock.valuation.layer"]
        for _iteration in range(2):
            clones |= adjustment.copy(
                {
                    "stock_valuation_layer_id": origin.id,
                    "account_move_line_id": adjustment.account_move_line_id.id,
                    "value": adjustment.value,
                }
            )
            origin.remaining_value += adjustment.value
        self.assertAlmostEqual(
            self._total_value(), self.BILL_PRICE + 2 * self.DIFF, places=2
        )

        wizard = self.env["pdiff.cleanup.wizard"].create(
            {
                "company_ids": [Command.set(self.company.ids)],
                "product_ids": [Command.set(self.product.ids)],
            }
        )
        wizard.action_analyze()
        self.assertEqual(wizard.state, "analyzed")
        self.assertEqual(wizard.surplus_count, 2)
        self.assertAlmostEqual(wizard.surplus_value, 2 * self.DIFF, places=2)

        wizard.action_apply()
        self.assertEqual(wizard.state, "done")
        self.assertAlmostEqual(self._total_value(), self.BILL_PRICE, places=2)
        self.assertAlmostEqual(self.product.standard_price, self.BILL_PRICE, places=2)

    def test_08_cleanup_wizard_is_idempotent(self):
        """Volver a ejecutar el asistente no vuelve a corregir lo ya corregido."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)
        adjustment = self._layers.filtered("pdiff_is_adjustment")
        origin = adjustment.stock_valuation_layer_id
        adjustment.copy(
            {
                "stock_valuation_layer_id": origin.id,
                "account_move_line_id": adjustment.account_move_line_id.id,
                "value": adjustment.value,
            }
        )
        origin.remaining_value += adjustment.value

        wizard = self.env["pdiff.cleanup.wizard"].create(
            {
                "company_ids": [Command.set(self.company.ids)],
                "product_ids": [Command.set(self.product.ids)],
            }
        )
        wizard.action_analyze()
        wizard.action_apply()
        value_after = self._total_value()

        wizard2 = self.env["pdiff.cleanup.wizard"].create(
            {
                "company_ids": [Command.set(self.company.ids)],
                "product_ids": [Command.set(self.product.ids)],
            }
        )
        wizard2.action_analyze()
        self.assertEqual(wizard2.surplus_count, 0)
        self.assertAlmostEqual(self._total_value(), value_after, places=2)

    def test_09_unposted_bill_adjustment_is_detected(self):
        """Un ajuste de factura cancelada se detecta como erróneo."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)

        # Cancelar saltándose los ganchos del módulo, como ocurrió en el
        # histórico: `parent_state` está almacenado, hay que actualizarlo también.
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE account_move SET state = 'cancel' WHERE id = %s", (bill.id,)
        )
        self.env.cr.execute(
            "UPDATE account_move_line SET parent_state = 'cancel' WHERE move_id = %s",
            (bill.id,),
        )
        self.env.invalidate_all()

        wizard = self.env["pdiff.cleanup.wizard"].create(
            {
                "company_ids": [Command.set(self.company.ids)],
                "product_ids": [Command.set(self.product.ids)],
                "fix_duplicates": False,
                "fix_unposted": True,
            }
        )
        wizard.action_analyze()
        self.assertEqual(wizard.unposted_count, 1)
        wizard.action_apply()
        self.assertAlmostEqual(self._total_value(), self.RECEIPT_PRICE, places=2)

    def test_10_block_reset_to_draft(self):
        """El bloqueo opcional impide volver a borrador facturas valorizadas."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)

        self.company.pdiff_block_reset_to_draft = True
        user = self.env["res.users"].create(
            {
                "name": "Contador test",
                "login": "pdiff_tester",
                "company_id": self.company.id,
                "company_ids": [Command.set(self.company.ids)],
                "groups_id": [
                    Command.link(self.env.ref("account.group_account_manager").id)
                ],
            }
        )
        with self.assertRaises(UserError):
            bill.with_user(user).button_draft()

        # Con el permiso explícito sí puede.
        user.groups_id += self.env.ref(
            "purchase_stock_price_diff_control.group_pdiff_force_reset_to_draft"
        )
        bill.with_user(user).button_draft()
        self.assertEqual(bill.state, "draft")

    def test_11_install_repair_routine(self):
        """La rutina que ejecuta el post_init_hook corrige el histórico."""
        po = self._receive()
        self._bill(po, self.BILL_PRICE)

        # Semilla: el histórico tal como lo dejó el bug (ajuste repetido 3 veces).
        adjustment = self._layers.filtered("pdiff_is_adjustment")
        origin = adjustment.stock_valuation_layer_id
        for _iteration in range(3):
            adjustment.copy(
                {
                    "stock_valuation_layer_id": origin.id,
                    "account_move_line_id": adjustment.account_move_line_id.id,
                    "value": adjustment.value,
                }
            )
            origin.remaining_value += adjustment.value
        self.assertAlmostEqual(
            self._total_value(), self.BILL_PRICE + 3 * self.DIFF, places=2
        )

        layer_model = self.env["stock.valuation.layer"]
        summary = layer_model._pdiff_repair_all(
            product_ids=self.product.ids
        )
        self.assertEqual(summary["duplicate_layers"], 3)
        self.assertEqual(summary["reversals_created"], 3)
        self.assertAlmostEqual(self._total_value(), self.BILL_PRICE, places=2)
        self.assertAlmostEqual(self.product.standard_price, self.BILL_PRICE, places=2)
        self.assertAlmostEqual(origin.remaining_value, self.BILL_PRICE, places=2)

        # Idempotente: una segunda pasada no encuentra nada.
        again = layer_model._pdiff_repair_all(
            product_ids=self.product.ids
        )
        self.assertEqual(again["layers_to_reverse"], 0)
        self.assertAlmostEqual(self._total_value(), self.BILL_PRICE, places=2)

    def test_12_repair_respects_force_date(self):
        """Los asientos de corrección se fechan en el periodo indicado."""
        po = self._receive()
        self._bill(po, self.BILL_PRICE)
        adjustment = self._layers.filtered("pdiff_is_adjustment")
        origin = adjustment.stock_valuation_layer_id
        adjustment.copy(
            {
                "stock_valuation_layer_id": origin.id,
                "account_move_line_id": adjustment.account_move_line_id.id,
                "value": adjustment.value,
            }
        )
        origin.remaining_value += adjustment.value

        target = fields.Date.context_today(self.env["res.company"])
        self.env["stock.valuation.layer"]._pdiff_repair_all(
            product_ids=self.product.ids, force_date=target
        )
        reversals = self._layers.filtered("pdiff_reversal_of_id")
        self.assertTrue(reversals)
        for reversal in reversals:
            self.assertEqual(reversal.account_move_id.date, target)

    def _deliver(self, qty=1.0):
        """Saca del almacén la cantidad indicada (consume la capa de recepción)."""
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company.id)], limit=1
        )
        src = warehouse.lot_stock_id
        dest = self.env.ref("stock.stock_location_customers")
        picking = self.env["stock.picking"].with_company(self.company).create({
            "picking_type_id": warehouse.out_type_id.id,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "move_ids": [Command.create({
                "name": self.product.name,
                "product_id": self.product.id,
                "product_uom_qty": qty,
                "product_uom": self.product.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
            })],
        })
        picking.action_confirm()
        picking.move_ids.write({"quantity": qty, "picked": True})
        picking.button_validate()
        return picking

    def test_13_consumed_stock_corrects_against_expense(self):
        """Si la mercadería ya salió, el exceso vuelve al gasto, no al inventario.

        Revertir contra inventario dejaría el producto con valorización negativa
        y cantidad cero, que es justo lo que no debe pasar.
        """
        po = self._receive()
        self._bill(po, self.BILL_PRICE)

        # Histórico: el ajuste se aplicó dos veces.
        adjustment = self._layers.filtered("pdiff_is_adjustment")
        origin = adjustment.stock_valuation_layer_id
        adjustment.copy({
            "stock_valuation_layer_id": origin.id,
            "account_move_line_id": adjustment.account_move_line_id.id,
            "value": adjustment.value,
        })
        origin.remaining_value += adjustment.value

        # Toda la mercadería sale del almacén antes de corregir.
        self._deliver(1.0)
        self.assertAlmostEqual(self.product.quantity_svl, 0.0, places=4)
        value_before = self.product.value_svl

        self.env["stock.valuation.layer"]._pdiff_repair_all(
            product_ids=self.product.ids
        )

        # El inventario no puede quedar en negativo: sigue en el mismo valor.
        self.assertAlmostEqual(self.product.quantity_svl, 0.0, places=4)
        self.assertAlmostEqual(
            self.product.value_svl, value_before, places=2,
            msg="La corrección dejó el inventario descuadrado en lugar de ir al gasto",
        )

        # ...y el exceso se corrigió con un asiento contra el gasto.
        reversal = self._layers.filtered("pdiff_reversal_of_id")
        self.assertTrue(reversal.pdiff_expense_move_id, "Falta el asiento de gasto")
        move = reversal.pdiff_expense_move_id
        self.assertEqual(move.state, "posted")
        self.assertAlmostEqual(
            sum(move.line_ids.filtered(lambda l: l.balance > 0).mapped("balance")),
            self.DIFF, places=2,
        )

    def test_14_delete_valuation_when_stock_on_hand(self):
        """La accion borra el par ajuste+reversion cuando la mercaderia sigue en almacen."""
        po = self._receive()
        bill = self._bill(po, self.BILL_PRICE)
        bill.button_draft()
        bill.action_post()

        self.assertEqual(len(self._layers), 4)  # recepcion + 2 ajustes + 1 reversion
        self.assertAlmostEqual(self._total_value(), self.BILL_PRICE, places=2)

        # Seleccionar el ajuste revertido: debe arrastrar su reversion.
        reversal = self._layers.filtered("pdiff_reversal_of_id")
        reversal.pdiff_reversal_of_id.action_pdiff_delete_valuation()

        layers = self._layers
        self.assertEqual(len(layers), 2, "Debian quedar solo recepcion y ajuste vigente")
        self.assertAlmostEqual(self._total_value(), self.BILL_PRICE, places=2)
        self.assertAlmostEqual(self.product.standard_price, self.BILL_PRICE, places=2)
        origin = layers.filtered(lambda l: not l.stock_valuation_layer_id)
        self.assertAlmostEqual(origin.remaining_value, self.BILL_PRICE, places=2)

    def test_15_delete_valuation_blocked_when_consumed(self):
        """Si la mercaderia ya salio, la accion se niega y explica por que."""
        po = self._receive()
        self._bill(po, self.BILL_PRICE)
        adjustment = self._layers.filtered("pdiff_is_adjustment")
        origin = adjustment.stock_valuation_layer_id
        adjustment.copy({
            "stock_valuation_layer_id": origin.id,
            "account_move_line_id": adjustment.account_move_line_id.id,
            "value": adjustment.value,
        })
        origin.remaining_value += adjustment.value
        self._deliver(1.0)
        self.env["stock.valuation.layer"]._pdiff_repair_all(product_ids=self.product.ids)

        value_before = self.product.value_svl
        target = self._layers.filtered("pdiff_reversal_of_id").pdiff_reversal_of_id
        with self.assertRaises(UserError):
            target.action_pdiff_delete_valuation()
        self.assertAlmostEqual(self.product.value_svl, value_before, places=2)

    def test_16_repair_deletes_safe_pairs_automatically(self):
        """Instalar y ya: lo que se puede borrar se borra, sin tocar nada a mano."""
        po = self._receive()
        self._bill(po, self.BILL_PRICE)
        adjustment = self._layers.filtered("pdiff_is_adjustment")
        origin = adjustment.stock_valuation_layer_id
        for _i in range(2):
            adjustment.copy({
                "stock_valuation_layer_id": origin.id,
                "account_move_line_id": adjustment.account_move_line_id.id,
                "value": adjustment.value,
            })
            origin.remaining_value += adjustment.value
        self.assertEqual(len(self._layers), 4)

        self.env["stock.valuation.layer"].action_pdiff_repair()

        layers = self._layers
        self.assertEqual(len(layers), 2, "Los pares anulados debian quedar borrados")
        self.assertFalse(layers.filtered("pdiff_reversal_of_id"))
        self.assertAlmostEqual(self._total_value(), self.BILL_PRICE, places=2)
        self.assertAlmostEqual(self.product.standard_price, self.BILL_PRICE, places=2)
        self.assertAlmostEqual(origin.remaining_value, self.BILL_PRICE, places=2)

    def test_17_consumed_keeps_reversal_and_is_not_deleted(self):
        """Con mercaderia consumida no se borra nada: queda la anulacion."""
        po = self._receive()
        self._bill(po, self.BILL_PRICE)
        adjustment = self._layers.filtered("pdiff_is_adjustment")
        origin = adjustment.stock_valuation_layer_id
        adjustment.copy({
            "stock_valuation_layer_id": origin.id,
            "account_move_line_id": adjustment.account_move_line_id.id,
            "value": adjustment.value,
        })
        origin.remaining_value += adjustment.value
        self._deliver(1.0)
        value_before = self.product.value_svl

        self.env["stock.valuation.layer"].action_pdiff_repair()

        self.assertTrue(self._layers.filtered("pdiff_reversal_of_id"),
                        "La anulacion debe permanecer cuando la mercaderia ya salio")
        self.assertAlmostEqual(self.product.value_svl, value_before, places=2)
        self.assertEqual(self.env["stock.valuation.layer"]._pdiff_count_safe_deletable(), 0)


@tagged("post_install", "-at_install")
class TestPriceDiffCron(TransactionCase):
    def test_cron_completion_uses_scheduler_progress(self):
        cron = self.env.ref("purchase_stock_price_diff_control.ir_cron_pdiff_repair")
        cron, progress = cron._add_progress()
        layers = self.env["stock.valuation.layer"].with_context(cron.env.context)
        # No real historical corrections: exercise completion with the same
        # progress context as the scheduler, which locks the cron separately.
        with patch.object(type(layers), "_pdiff_repair_all", return_value={"layers_to_reverse": 0}), \
             patch.object(type(layers), "_pdiff_delete_safe_pairs", return_value=0), \
             patch.object(type(layers), "_pdiff_count_pending", return_value=0), \
             patch.object(type(layers), "_pdiff_count_safe_deletable", return_value=0), \
             patch.object(type(cron), "write", side_effect=AssertionError("Running cron must not write its locked row")):
            layers._pdiff_cron_repair()
        self.assertTrue(progress.deactivate)
        self.assertEqual(progress.remaining, 0)
