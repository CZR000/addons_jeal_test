# -*- coding: utf-8 -*-
{
    "name": "Stock Request - Permissions",
    "summary": """
        Extiende las solicitudes de existencias con control avanzado de permisos para la edición y aprobación.
    """,
    "description": """
        Este módulo añade controles de permisos a las solicitudes de existencias, permitiendo gestionar la edición 
        y aprobación de campos específicos únicamente para usuarios con permisos designados. Esto proporciona 
        un mayor control y seguridad en la gestión de solicitudes de existencias.

        Características principales:
        - Control de permisos de edición basados en roles de usuario.
        - Configuración de aprobación de solicitudes.
        - Totalmente integrado con el módulo base de solicitudes de existencias (stock_request).
        - Mejora la seguridad y auditoría del proceso de solicitud de existencias.
    """,
    "author": "JEAL",
    "website": "https://www.jeal.com",
    "category": "Inventory",
    "version": "18.0.0.3.3",
    "license": "LGPL-3",
    "depends": [
        "base",
        "stock_request",
        "fork_custom",
    ],
    "data": [
        "security/stock_request_security.xml",
        "security/ir.model.access.csv",
        "views/stock_request_inh_view.xml",
        "views/stock_request_order_inh_view.xml",
        "report/identity_card_fork_inh.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
