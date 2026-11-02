# -*- coding: utf-8 -*-
{
    "name": "Empleados - Actualización Automática de Contacto",
    "summary": """
        Sincroniza automáticamente el nombre del empleado con el registro de contacto vinculado (res.partner).
    """,
    "description": """
        Este módulo asegura que los campos de nombre y apellidos del empleado en la sección 
        "Información Privada" del módulo de Empleados se sincronicen automáticamente con el 
        registro de contacto correspondiente (res.partner). Cuando se crea o actualiza el 
        nombre o apellidos de un empleado, la información del contacto vinculado se actualiza 
        en consecuencia. Esto evita la creación de contactos duplicados y mantiene los datos 
        consistentes entre los registros de empleados y contactos.
    """,
    "author": "SINETICS",
    "website": "https://www.sinetics.com",
    "category": "Human Resources",
    "version": "18.0.0.3.6",
    "depends": [
        "base",
        "hr",
        "first_and_last_name",
    ],
    "data": [
        "views/res_partner_inh_views.xml",
    ],
    "license": "LGPL-3",
}
