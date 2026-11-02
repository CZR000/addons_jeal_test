"""
Migrar el tipo de cambio forzado de la convención inversa a la comercial.

Hasta la versión 18.0.2.0.0, el módulo redefinía ``to_force_exchange_rate`` como una columna almacenada en ``account_bank_statement_line``, replicando el campo delegado de
``account.move`` y manteniendo el tipo de cambio **inverso** (0.2857). A partir de la versión 18.0.3.0.0, el tipo de cambio se encuentra en ``forced_exchange_rate`` con la convención **comercial** (3.5000)
y se vuelve a utilizar el campo delegado.

La columna anterior se mantiene intencionadamente: eliminarla es irreversible y
Odoo simplemente la ignora. Elimínela manualmente una vez que se haya validado la migración.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'account_bank_statement_line'
           AND column_name = 'to_force_exchange_rate'
    """)
    if not cr.rowcount:
        return

    cr.execute("""
        UPDATE account_bank_statement_line
           SET forced_exchange_rate = 1.0 / to_force_exchange_rate
         WHERE to_force_exchange_rate > 0
           AND COALESCE(forced_exchange_rate, 0) = 0
    """)

    env = api.Environment(cr, SUPERUSER_ID, {})
    st_lines = env["account.bank.statement.line"].search(
        [("forced_exchange_rate", ">", 0)]
    )
    st_lines.modified(["forced_exchange_rate"])
    st_lines.flush_recordset()
