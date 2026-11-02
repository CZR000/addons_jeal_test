{
    'name': 'Restricción de Creación de Diarios',
    'version': '18.0.1.0.1',
    'category': 'Accounting',
    'summary': 'Controla los permisos de creación de diarios contables',
    'description': """
        Módulo para Odoo 18 que permite restringir la creación de diarios contables.

        Características:
        - Nuevo grupo de seguridad: "Puede crear diarios"
        - Solo usuarios con este permiso pueden crear nuevos diarios
        - Los demás usuarios solo pueden ver y editar diarios existentes
    """,
    'author': 'Leo Daniel FS',
    'depends': ['account'],
    'data': [
        'security/security_groups.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
