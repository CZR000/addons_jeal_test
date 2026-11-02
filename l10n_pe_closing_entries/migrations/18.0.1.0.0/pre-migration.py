# -*- coding: utf-8 -*-
"""Migra la configuración de detalle del asiento de cierre.

`detailed_by_product` (booleano) se sustituye por `closing_detail` (selección),
que permite además el desglose por contacto. La conversión se hace en SQL, en
pre-migration, para que el ORM encuentre la columna ya poblada al cargar el
nuevo campo y no la inicialice con el valor por defecto.
"""
import logging

_logger = logging.getLogger(__name__)


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = %s
           AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        "ALTER TABLE account_account ADD COLUMN IF NOT EXISTS closing_detail VARCHAR"
    )

    if _column_exists(cr, "account_account", "detailed_by_product"):
        cr.execute(
            """
            UPDATE account_account
               SET closing_detail = CASE
                       WHEN detailed_by_product IS TRUE THEN 'product'
                       ELSE 'none'
                   END
             WHERE closing_detail IS NULL
            """
        )
        _logger.info(
            "closing_detail poblado desde detailed_by_product (%s filas)", cr.rowcount
        )
        # La columna obsoleta se elimina explícitamente: Odoo retira el campo de
        # `ir.model.fields` al actualizar el módulo, pero deja la columna en BD.
        cr.execute("ALTER TABLE account_account DROP COLUMN IF EXISTS detailed_by_product")

    cr.execute("UPDATE account_account SET closing_detail = 'none' WHERE closing_detail IS NULL")

    # `closing_depth` es un campo calculado almacenado nuevo: se crea la columna
    # vacía para que el post-migration pueda recalcularla en bloque.
    cr.execute(
        "ALTER TABLE account_account ADD COLUMN IF NOT EXISTS closing_depth INTEGER"
    )
