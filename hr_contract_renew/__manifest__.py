# -*- coding: utf-8 -*-
{
    # --- Metadatos Principales del Módulo ---
    "name": "Renovación de Contratos",
    "summary": """
        Automatiza el proceso de renovación de contratos de empleados, desde la selección hasta la creación automática del nuevo contrato.
    """,
    "description": """
        ## Proceso de Renovación de Contratos Automatizado\n
        Este módulo introduce un flujo de trabajo completo para gestionar la renovación de contratos de empleados de manera eficiente:\n
        1.  **Creación de Lotes:** Genere procesos de renovación por rangos de fecha.\n
        2.  **Población Automática:** El sistema busca y añade todos los contratos que están por vencer en el periodo seleccionado.\n
        3.  **Aprobación Manual:** El equipo de RRHH revisa las líneas, ajusta salarios o fechas y aprueba las renovaciones deseadas.\n
        4.  **Creación Programada:** Una tarea automática (CRON) se ejecuta diariamente y crea los nuevos contratos un día antes de que los antiguos expiren, asegurando una transición sin interrupciones.
    """,
    # --- Información del Autor y Soporte ---
    "author": "SINETICS",
    "website": "https://www.sinetics.com",
    "maintainers": ["sinetics_dev"],
    "license": "LGPL-3",
    # --- Clasificación y Versión ---
    "category": "Human Resources/Contracts",
    "version": "18.0.0.1.3",
    # --- Dependencias de Odoo ---
    "depends": [
        "hr",
        "hr_contract",
        "hr_payroll",
    ],
    # --- Archivos de Datos y Vistas ---
    "data": [
        "security/ir.model.access.csv",
        "security/hr_contract_renew_security.xml",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "views/hr_contract_renew_views.xml",
        "views/menuitems.xml",
    ],
    # --- Atributos de Instalación ---
    "installable": True,
    "application": False,
    "auto_install": False,
}
