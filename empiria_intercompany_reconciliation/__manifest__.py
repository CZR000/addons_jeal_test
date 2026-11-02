# -*- coding: utf-8 -*-
{
    "name": "Conciliación intercompany por documento (Grupo Empiria)",
    "version": "18.0.1.3.1",
    "category": "Accounting/Accounting",
    "summary": "Para cada par de empresas del grupo, si sus saldos cuadran a una fecha "
               "de corte y, si no, qué documento o movimiento lo explica y qué hacer",
    "description": """
Conciliación intercompany por documento
=======================================

Reporte de control (no crea ni modifica asientos): para cada par de empresas del
grupo y bloque de cuentas (Comercial: 12, 13, 14, 19 / 41-45, 47, incluidos los
anticipos 122 y 4220; Préstamos y otros: 16, 17 / 46) compara el saldo de A con B
contra el de B con A a una fecha de corte y explica la diferencia por documento
con 15 reglas en cascada (comprobante por número, serie o número distinto,
anticipos aplicados, pagos y cobros, pagos agrupados, compensación entre tres
empresas, cuenta distinta entre bloques, diferencia de cambio...).

- Asistente con fecha de corte y empresas; resumen por par con una columna por
  categoría y control (diferencia - categorías = 0); detalle con qué hacer.
- Marcar revisado con comentario y emparejar a mano: se conservan entre
  ejecuciones (si cambia el importe del documento, vuelve a pendiente).
- Exportación a Excel (Notas, Resumen, Por categoría, Detalle, Emparejamientos
  manuales, Reglas).
- Ejecución diaria programada con aviso al responsable si hay pendientes nuevos
  o el control de algún par no es 0.
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "LGPL-3",
    "depends": ["account", "mail", "l10n_latam_invoice_document"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ic_reconciliation_data.xml",
        "wizard/ic_reconciliation_generate_views.xml",
        "wizard/ic_reconciliation_review_wizard_views.xml",
        "wizard/ic_reconciliation_match_wizard_views.xml",
        "views/ic_reconciliation_line_views.xml",
        "views/ic_reconciliation_pair_views.xml",
        "views/ic_reconciliation_run_views.xml",
        "views/ic_reconciliation_config_views.xml",
        "views/ic_reconciliation_menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
