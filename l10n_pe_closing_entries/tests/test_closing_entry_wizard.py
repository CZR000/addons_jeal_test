# -*- coding: utf-8 -*-
from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestClosingEntryWizard(AccountTestInvoicingCommon):
    """Cubre la cadena de cierre multinivel y la idempotencia de la corrida."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.journal = cls.company_data["default_journal_misc"]

        cls.account_59 = cls._create_account("591000", "Resultados Acumulados", "equity")
        cls.account_89 = cls._create_account(
            "891000", "Determinacion del Resultado", "equity", closing=cls.account_59
        )
        cls.account_60 = cls._create_account(
            "601000", "Compras", "expense", closing=cls.account_89
        )
        cls.account_70 = cls._create_account(
            "701000", "Ventas", "income", closing=cls.account_89
        )
        cls.account_10 = cls._create_account("101000", "Caja", "asset_cash")

        cls.date_from = fields.Date.to_date("2025-01-01")
        cls.date_to = fields.Date.to_date("2025-12-31")
        cls.closing_date = fields.Date.to_date("2025-12-31")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @classmethod
    def _create_account(cls, code, name, account_type, closing=None):
        return cls.env["account.account"].create(
            {
                "code": code,
                "name": name,
                "account_type": account_type,
                "company_ids": [Command.link(cls.company.id)],
                "closing_account_id": closing.id if closing else False,
            }
        )

    def _post_move(self, lines):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.journal.id,
                "date": self.date_to,
                "line_ids": [Command.create(vals) for vals in lines],
            }
        )
        move.action_post()
        return move

    def _new_wizard(self, **values):
        defaults = {
            "company_id": self.company.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "closing_date": self.closing_date,
            "journal_id": self.journal.id,
            "analytic_mode": "ignore",
        }
        defaults.update(values)
        return self.env["closing.entry.wizard"].create(defaults)

    def _closing_moves(self):
        return self.env["account.move"].search(
            [("is_closing_entry", "=", True), ("company_id", "=", self.company.id)]
        )

    def _balance_of(self, account, moves):
        lines = moves.line_ids.filtered(lambda line: line.account_id == account)
        return sum(lines.mapped("balance"))

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    def test_closing_depth_is_computed_along_the_chain(self):
        self.assertEqual(self.account_59.closing_depth, 0)
        self.assertEqual(self.account_89.closing_depth, 1)
        self.assertEqual(self.account_60.closing_depth, 2)

    def test_is_closing_account_is_derived_from_sources(self):
        self.assertTrue(self.account_89.is_closing_account)
        self.assertTrue(self.account_59.is_closing_account)
        self.assertFalse(self.account_10.is_closing_account)

    def test_recursive_chain_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.account_59.closing_account_id = self.account_60

    # ------------------------------------------------------------------
    # Cadena multinivel
    # ------------------------------------------------------------------
    def test_multilevel_chain_generates_one_move_per_level(self):
        self._post_move(
            [
                {"account_id": self.account_60.id, "debit": 1000.0, "credit": 0.0},
                {"account_id": self.account_10.id, "debit": 0.0, "credit": 1000.0},
            ]
        )
        self._post_move(
            [
                {"account_id": self.account_10.id, "debit": 1500.0, "credit": 0.0},
                {"account_id": self.account_70.id, "debit": 0.0, "credit": 1500.0},
            ]
        )

        self._new_wizard(entry_grouping="level").action_generate_entries()
        moves = self._closing_moves()

        levels = sorted(moves.mapped("closing_level"))
        self.assertEqual(levels, [1, 2], "Debe generarse un asiento por nivel")

        level_2 = moves.filtered(lambda move: move.closing_level == 2)
        level_1 = moves.filtered(lambda move: move.closing_level == 1)

        # Nivel 2: 60 y 70 se saldan contra 89.
        self.assertEqual(self._balance_of(self.account_60, level_2), -1000.0)
        self.assertEqual(self._balance_of(self.account_70, level_2), 1500.0)
        self.assertEqual(self._balance_of(self.account_89, level_2), -500.0)

        # Nivel 1: 89 se salda contra 59, en un asiento independiente.
        self.assertEqual(self._balance_of(self.account_89, level_1), 500.0)
        self.assertEqual(self._balance_of(self.account_59, level_1), -500.0)
        self.assertFalse(level_1.line_ids.account_id & (self.account_60 | self.account_70))

    def test_moves_are_balanced(self):
        self._post_move(
            [
                {"account_id": self.account_60.id, "debit": 700.0, "credit": 0.0},
                {"account_id": self.account_10.id, "debit": 0.0, "credit": 700.0},
            ]
        )
        self._new_wizard().action_generate_entries()
        for move in self._closing_moves():
            self.assertAlmostEqual(sum(move.line_ids.mapped("balance")), 0.0, places=2)

    # ------------------------------------------------------------------
    # Idempotencia
    # ------------------------------------------------------------------
    def test_second_run_does_not_duplicate_draft_entries(self):
        self._post_move(
            [
                {"account_id": self.account_60.id, "debit": 900.0, "credit": 0.0},
                {"account_id": self.account_10.id, "debit": 0.0, "credit": 900.0},
            ]
        )
        self._new_wizard().action_generate_entries()
        first_run = self._closing_moves()
        self.assertTrue(first_run)
        self.assertEqual(set(first_run.mapped("state")), {"draft"})

        with self.assertRaises(UserError):
            self._new_wizard().action_generate_entries()
        self.assertEqual(self._closing_moves(), first_run)

    def test_replace_drafts_regenerates_the_period(self):
        self._post_move(
            [
                {"account_id": self.account_60.id, "debit": 400.0, "credit": 0.0},
                {"account_id": self.account_10.id, "debit": 0.0, "credit": 400.0},
            ]
        )
        self._new_wizard().action_generate_entries()
        first_run_ids = self._closing_moves().ids

        self._new_wizard(replace_drafts=True).action_generate_entries()
        second_run = self._closing_moves()

        self.assertTrue(second_run)
        self.assertFalse(set(second_run.ids) & set(first_run_ids))

    def test_only_accounts_with_pending_balance_are_closed(self):
        self._post_move(
            [
                {"account_id": self.account_60.id, "debit": 300.0, "credit": 0.0},
                {"account_id": self.account_10.id, "debit": 0.0, "credit": 300.0},
            ]
        )
        self._new_wizard().action_generate_entries()
        closed_accounts = self._closing_moves().line_ids.account_id
        self.assertNotIn(self.account_70, closed_accounts)

    # ------------------------------------------------------------------
    # Detalle
    # ------------------------------------------------------------------
    def test_detail_by_partner_splits_lines(self):
        partner_a = self.env["res.partner"].create({"name": "Cliente A"})
        partner_b = self.env["res.partner"].create({"name": "Cliente B"})
        self.account_70.closing_detail = "partner"
        self._post_move(
            [
                {
                    "account_id": self.account_70.id,
                    "partner_id": partner_a.id,
                    "debit": 0.0,
                    "credit": 100.0,
                },
                {
                    "account_id": self.account_70.id,
                    "partner_id": partner_b.id,
                    "debit": 0.0,
                    "credit": 250.0,
                },
                {"account_id": self.account_10.id, "debit": 350.0, "credit": 0.0},
            ]
        )
        self._new_wizard().action_generate_entries()

        lines = self._closing_moves().line_ids.filtered(
            lambda line: line.account_id == self.account_70
        )
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines.partner_id, partner_a | partner_b)

    def test_action_does_not_hide_draft_moves(self):
        """La acción devuelta no debe arrastrar `search_default_posted`.

        `account.action_move_journal_line` lo trae por defecto y ocultaría los
        asientos de cierre en borrador recién generados.
        """
        self._post_move(
            [
                {"account_id": self.account_60.id, "debit": 120.0, "credit": 0.0},
                {"account_id": self.account_10.id, "debit": 0.0, "credit": 120.0},
            ]
        )
        action = self._new_wizard().action_generate_entries()
        context = action.get("context") or {}
        self.assertFalse(
            [key for key in context if key.startswith("search_default_")],
            "La acción no debe aplicar filtros por defecto sobre los asientos creados",
        )

    def test_closing_date_outside_period_stays_idempotent(self):
        """La fecha del asiento puede caer fuera del periodo cerrado."""
        self._post_move(
            [
                {"account_id": self.account_60.id, "debit": 640.0, "credit": 0.0},
                {"account_id": self.account_10.id, "debit": 0.0, "credit": 640.0},
            ]
        )
        later = fields.Date.to_date("2026-03-31")
        self._new_wizard(closing_date=later).action_generate_entries()
        first_run = self._closing_moves()
        self.assertTrue(first_run)
        self.assertEqual(set(first_run.mapped("date")), {later})

        with self.assertRaises(UserError):
            self._new_wizard(closing_date=later).action_generate_entries()
        self.assertEqual(self._closing_moves(), first_run)

    def test_nothing_configured_raises(self):
        (self.account_60 | self.account_70 | self.account_89).write(
            {"closing_account_id": False}
        )
        with self.assertRaises(UserError):
            self._new_wizard().action_generate_entries()
