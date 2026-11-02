# -*- coding: utf-8 -*-
{
    "name": "Perú - Redondeo de Cambio en Anticipos",
    "version": "18.0.1.1.0",
    "category": "Accounting/Localizations",
    "summary": "Reclasifica el residuo de redondeo por tipo de cambio de las "
               "facturas con anticipo a la cuenta de diferencia de cambio",
    "description": """
Cuando una factura en moneda extranjera se salda completamente con un anticipo
aplicado como línea/concepto, el importe en divisa queda en cero pero, por el
redondeo a céntimos de cada línea, puede quedar un pequeño residuo en moneda de
la compañía (soles). Ese residuo lo absorbe la línea por cobrar (cuenta 12) y,
como en divisa la factura está saldada, nunca se concilia: queda como un saldo
"por redondeo" en el Reporte de Ventas.

Este módulo reclasifica ese residuo dentro del mismo asiento, dejando la línea
por cobrar en cero y llevando la diferencia a la cuenta de diferencia de cambio
configurada en la compañía (ganancia 77x / pérdida 67x), igual que se hace en el
flujo de pagos. Se aplica automáticamente al publicar (post) y ofrece una acción
para corregir los asientos ya existentes.
""",
    "author": "Empiria",
    "depends": [
        "account",
        "l10n_pe_advance_global_discount",
    ],
    "data": [
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "Other proprietary",
}
