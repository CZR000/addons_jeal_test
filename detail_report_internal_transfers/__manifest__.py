# -*- coding: utf-8 -*-
{
    "name": "Informe Detalle de Transferencias Internas",
    "summary": "Genera reportes detallados en PDF y Excel (XLSX) sobre las transferencias de almacén.",
    "description": """
        Reporte Detallado de Transferencias de Almacén
        ==============================================
        Este módulo añade un asistente (wizard) avanzado en el módulo de Inventario para generar 
        reportes de transferencias filtrados por fecha, estado, productos y tipo de operación.

        Formatos soportados:
        --------------------
        * PDF (Resumen logístico)
        * Excel / XLSX (Detalle analítico extendido con datos de la última compra)
    """,
    "author": "SINETICS",
    "website": "https://www.sinetics.com",
    "category": "Inventory/Inventory",
    "version": "18.0.1.0.0",
    "license": "OPL-1",
    "depends": [
        "stock",
        "purchase",
        "report_xlsx",
    ],
    "data": [
        "security/ir.model.access.csv",
        "report/report_informe_bank.xml",
        "report/report_action.xml",
        "wizard/report_internal_transfers_view.xml",
        "views/menuitems.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
