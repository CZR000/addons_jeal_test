# -*- coding: utf-8 -*-
{
    "name": "Reporte de Ventas Profesional",
    "summary": "Diseño de presupuesto personalizado con 3 logos, garantía dinámica y marca de agua.",
    "description": """
        Personalización avanzada del PDF de Ventas:
        - Soporte para 3 imágenes (Logo izq, Logo der, Marca de agua).
        - Términos y Garantía editables por venta (HTML).
        - Sección de cuentas bancarias y footer configurable por compañía.
        - Diseño de tabla con imágenes de producto.
    """,
    "author": "EMPIRIA",
    "website": "https://www.empiria.com",
    "category": "Sales/Sales",
    "version": "18.0.1.1.6",
    "depends": [
        "base",
        "sale",
        "sale_management",
        "web",
        "account_field_to_force_exchange_rate",
        "account_forced_exchange_rate_extended",
    ],
    "data": [
        "report/sale_report_template.xml",
        "report/sale_report_action.xml",
        "views/res_company_views.xml",
        "views/sale_order_views.xml",
        "views/product_product_views.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "custom_sale_report_pro/static/src/scss/report_styles.scss",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
