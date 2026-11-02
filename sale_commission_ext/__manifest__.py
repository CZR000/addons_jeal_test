# -*- coding: utf-8 -*-
{
    "name": "Comisiones de venta - moneda del plan y facturas publicadas",
    "version": "18.0.1.0.0",
    "category": "Sales/Commission",
    "summary": "Planes de comisión en soles o dólares y logros solo sobre facturas publicadas",
    "description": """
Extiende los Planes de comisión (sale_commission):

1. Moneda del plan: cada plan puede estar en la moneda de la compañía o en otra
   (p.ej. USD). Objetivos, niveles de comisión, logros y comisión se expresan en
   esa moneda. Los documentos en la moneda del plan suman su importe exacto; los
   demás se convierten con el tipo de cambio de su propia fecha. Un plan en la
   moneda de la compañía calcula exactamente igual que el estándar.
2. Solo facturas publicadas: los logros por importe/cantidad facturada ya no
   consideran facturas en borrador.
3. Ajustes manuales en otra moneda: se convierten correctamente a la moneda del
   plan (el estándar multiplicaba por la tasa en vez de dividir).
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "OEEL-1",
    "depends": [
        "sale_commission",
    ],
    "data": [
        "views/sale_commission_plan_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
