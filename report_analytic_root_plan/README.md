# report_analytic_root_plan

Módulo Odoo 18 Enterprise que agrega un filtro **"Planes raíz"** al dropdown Analítica de los reportes financieros y una fila visual extra en el header agrupando las cuentas analíticas por su plan raíz.

## Alcance v1

- Filtro "Planes raíz" en el dropdown Analítica.
- Al seleccionar planes raíz: reemplaza las cuentas manuales por todas las cuentas del/los plan(es).
- Fila extra en el header (agrupamiento visual) en vista web y export PDF.

**No incluido en v1:** export XLSX (pendiente v1.1).

## Instalación

1. Copiar la carpeta a un addons_path.
2. Actualizar la lista de módulos y buscar "Reportes: filtro y agrupación por plan raíz analítico".
3. Instalar.

## Prueba

1. Ir al reporte P&G (o cualquier reporte con soporte de analytic_groupby).
2. Clic en el segundo botón "Analítica" (el que tiene "Accounts" y "Plans").
3. Ahora aparece también "Planes raíz".
4. Seleccionar uno o varios planes raíz → las cuentas se autorellenan y aparece el encabezado agrupador.

## Estructura

```
report_analytic_root_plan/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── account_report.py           # backend: initializer y render_data
├── views/
│   └── account_report_templates.xml  # extensión PDF
└── static/src/components/account_report/
    ├── filters/filter_analytic_groupby.xml   # Owl: dropdown
    └── header/header.xml                     # Owl: header de tabla
```

## Notas técnicas

- El nuevo initializer `_init_options_root_plan_groupby` corre en secuencia 994, justo antes del initializer nativo `_init_options_analytic_groupby` (995), mutando `previous_options` para inyectarle las cuentas del plan raíz.
- El override de `_get_column_headers_render_data` agrega la clave `root_plan_row` con colspans variables por plan.
- Los templates (PDF y Owl) reemplazan el foreach de `column_headers` para intercalar la fila extra entre nivel 0 (fecha) y nivel 1 (cuentas).

## v1.1 pendiente

- Override de `_inject_report_into_xlsx_sheet` para paridad en XLSX.
- (Eventual) opción de dedupliación de cuentas con mismo nombre + mismo plan raíz.
