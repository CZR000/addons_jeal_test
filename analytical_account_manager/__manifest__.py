# -*- coding: utf-8 -*-
{
    "name": "Gestión de Cuentas Analíticas en Albaranes",
    "summary": "Asignación y propagación de cuentas analíticas desde el inventario hacia los asientos contables.",
    "description": """
        Gestión de Cuentas Analíticas en Operaciones de Inventario
        ==========================================================
        Este módulo permite la inyección de dimensiones analíticas directamente en las transferencias de stock (albaranes) y asegura su correcta propagación a la contabilidad.

        Características principales:
        ----------------------------
        * Asignación de Plan y Cuenta Analítica en la cabecera y líneas del albarán.
        * Propagación automática hacia las Capas de Valoración (SVL).
        * Inyección de centros de costos en los Asientos Contables generados.
        * Soporte nativo para devoluciones (propaga el plan y la cuenta desde la operación original).
    """,
    "author": "SINETICS",
    "website": "https://www.sinetics.com",
    "category": "Inventory",
    "version": "18.0.1.0.2",
    "license": "OPL-1",
    "depends": [
        "stock",
        "account",
        "analytic",
        "stock_account",
    ],
    "data": [
        "views/stock_picking_type_inh_view.xml",
        "views/stock_picking_inh_view.xml",
        "views/stock_move_line_inh_view.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
