# -*- coding: utf-8 -*-
{
    "name": "Perú - Ubicación de Activos",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": "Ubicación del activo (distrito, provincia, ciudad, dirección) "
               "y casilla de comentarios para el alta del activo",
    "description": """
Agrega al activo (account.asset) una sección de ubicación con los mismos campos
que la dirección de contactos en Perú: Dirección, Provincia, Distrito y Ciudad.
El distrito se filtra por la provincia seleccionada (y al elegir el distrito se
autocompleta su provincia). Incluye además una casilla de comentarios para el
alta del activo.
""",
    "author": "Empiria",
    "depends": [
        "account_asset",
        "l10n_pe",
    ],
    "data": [
        "views/account_asset_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "Other proprietary",
}
