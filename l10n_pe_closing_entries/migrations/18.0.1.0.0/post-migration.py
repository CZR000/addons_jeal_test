# -*- coding: utf-8 -*-
"""Recalcula los campos derivados de la nueva cadena de cierre.

`is_closing_account` pasa a derivarse de las cuentas que apuntan a ella
(`closing_source_ids`), y `closing_depth` de la longitud de la cadena. Ambos
son `store=True`, por lo que se fuerza su recálculo una sola vez tras la
actualización.

`is_closing_account` conserva `readonly=False`: si un usuario necesita marcar
manualmente una cuenta que todavía no es destino de ninguna otra, puede
hacerlo; el recálculo sólo se dispara al cambiar `closing_source_ids`.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    Account = env["account.account"]
    accounts = Account.with_context(active_test=False).search([])
    if not accounts:
        return

    # `closing_depth` es puramente derivado: se recalcula para todas las cuentas.
    env.add_to_compute(Account._fields["closing_depth"], accounts)

    # `is_closing_account` es editable: sólo se fuerza en las cuentas que ya son
    # destino de otra, para no machacar marcas puestas a mano.
    targets = accounts.mapped("closing_account_id")
    if targets:
        env.add_to_compute(Account._fields["is_closing_account"], targets)

    accounts.flush_recordset()

    chained = accounts.filtered(lambda account: account.closing_depth > 1)
    _logger.info(
        "Cierre contable: %s cuentas configuradas, %s con cadena de más de un nivel.",
        len(accounts.filtered("closing_account_id")),
        len(chained),
    )
