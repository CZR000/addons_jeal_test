{
    "name": "HR Contract Wage Restriction",
    "version": "18.0.1.0.1",
    "summary": "Restringe la visibilidad del campo sueldo en contratos según permisos de usuario",
    "description": """
        Agrega un grupo de seguridad "Ver Sueldo de Empleados" que controla
        la visibilidad del campo wage (sueldo) en todas las vistas:
        formulario, lista, kanban y búsqueda.
        Los usuarios sin este grupo no podrán ver ni exportar el sueldo.
        El campo también está protegido a nivel de modelo.
    """,
    "author": "Empiria",
    "category": "Human Resources",
    "depends": ["hr_contract"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/hr_contract_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
