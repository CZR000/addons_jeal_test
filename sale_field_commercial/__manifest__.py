# -*- coding: utf-8 -*-
{
    "name": "Sale: Campo Comercial de Venta",
    "summary": "Permite asignar contactos comerciales en órdenes de venta.",
    "description": """
        Este módulo permite vincular contactos comerciales (res.partner sin usuario asignado)
        a órdenes de venta. Útil para empresas que trabajan con empleados sin acceso directo al sistema.\n\n

        Características:\n
            - Campo personalizado en ventas para asignar comerciales.\n
            - Configuración por compañía para habilitar o deshabilitar esta funcionalidad.\n
            - Integración con vistas de lista y formulario de órdenes de venta.
    """,
    "author": "JEAL",
    "website": "https://www.jeal.com",
    "category": "Sales/Customization",
    "version": "18.0.0.1.7",
    "license": "AGPL-3",
    "depends": [
        "base",
        "sale",
        "account",
        "classic_format_invoice",
    ],
    "data": [
        "views/res_company_inh_view.xml",
        "views/sale_order_views_inh.xml",
        "views/account_move_inh_views.xml",
        "report/ir_actions_report_templates.xml",
        "report/report_invoice_classic_inh.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
