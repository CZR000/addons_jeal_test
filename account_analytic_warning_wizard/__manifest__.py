# -*- coding: utf-8 -*-
{
    "name": "Analítica Obligatoria en Cuentas de Destino",
    "summary": "Bloquea guardar y publicar asientos cuando falte analítica en cuentas con 'Usar Cuentas de Destino'.",
    "description": """
        Validación obligatoria en Asientos Contables:

        Si alguna línea del asiento usa una cuenta contable con 'Usar Cuentas de Destino'
        activado, la Distribución Analítica es obligatoria en esa línea.

        Bloquea tanto el guardado en borrador como la publicación del asiento.

        Excepción: si el diario del asiento tiene marcado 'No generar destinos', la
        validación se omite y no se exige la Distribución Analítica.
    """,
    "author": "EMPIRIA",
    "website": "https://www.empiria.com",
    "category": "Accounting",
    "version": "18.0.2.1.1",
    "depends": [
        "account",
        "analytic",
        "l10n_pe_destination_account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizards/account_analytic_check_wizard_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
}
