# -*- coding: utf-8 -*-
{
    "name": "Payslip Accounting with Analytic Restriction",
    "summary": "Restringe el uso de cuentas analíticas solo a cuentas contables del grupo 60 en asientos generados desde nómina.",
    "description": """
        Este módulo amplía la contabilidad de nómina en Odoo, modificando la creación de asientos contables 
        desde el modelo 'hr.payslip'. 
        \n\n
        ✅ **Funcionalidades principales**:\n
        - Solo permite la asignación de cuentas analíticas en cuentas contables del grupo 60 (Gastos).\n
        - Se aplica cuando el usuario genera asientos contables desde la nómina.\n
        - Mejora el control y la distribución de costos en la contabilidad de nómina.\n
    """,
    "author": "JEAL",
    "website": "https://www.jeal.com",
    "category": "Human Resources/Payroll",
    "version": "18.0.0.3.5",
    "license": "LGPL-3",
    "depends": [
        "hr_payroll_account",
    ],
    "data": [
        "views/account_account_inh_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
