# -*- coding: utf-8 -*-
{
    "name": "Perú - Rendición de Gastos: comprobantes de otra empresa del grupo",
    "version": '18.0.1.1.1',
    "category": "Human Resources/Expenses",
    "summary": "Rendir en una empresa gastos con comprobantes emitidos a otra empresa del grupo: "
               "cuenta por cobrar intercompany y factura en borrador en la empresa que asume el gasto",
    "description": """
Gastos con comprobantes de otra empresa del grupo (pedido P13, 13/10/2026)
==================================================================================

Un empleado de OMNI recibe un fondo y paga comprobantes emitidos a otra empresa
del grupo (JE-AL, Connected...). Rinde todo en un solo informe, en OMNI:

1. En cada línea, "Empresa que asume el gasto" (por defecto, la del informe) y el
   RUC del adquiriente que figura en el comprobante (debe ser el de esa empresa).
2. Al contabilizar el informe, en OMNI esas líneas no generan factura ni Registro
   de Compras: un asiento Debe cuenta por cobrar intercompany (1699000/1699001
   por defecto, configurable; p.ej. 1612000/1612001) a nombre de la otra empresa
   / Haber cuenta 14 del empleado, conciliado con el anticipo o el fondo.
3. En la empresa que asume el gasto se crea, con permisos del sistema, una
   factura de proveedor en BORRADOR con los datos del comprobante (proveedor,
   tipo de documento, serie-número, fecha, importe, impuestos por nombre). Nunca
   se publica sola; el empleado no necesita acceso a esa empresa. Solo en las
   empresas marcadas "Puede recibir gastos de otras empresas".
4. Lista "Gastos recibidos de otras empresas" (Contabilidad > Proveedores) para
   la contadora, con la empresa y el informe de origen.
5. Al publicar esa factura, la empresa reconoce su deuda: Debe 42 proveedor /
   Haber cuenta por pagar intercompany (4699000/4699001) a nombre de OMNI, con
   la misma referencia (número del informe) que el asiento de OMNI.
6. Restablecer el informe anula el asiento de OMNI y la factura en borrador; si
   la factura ya se publicó, avisa.

7. El RUC del adquiriente se completa con el de la empresa que asume el gasto;
   si se cambia por otro, se advierte (no bloquea).
8. La línea de la factura en borrador lleva producto: el mismo del gasto si existe
   en esa empresa (compartido o con el mismo código), el de la tabla de
   equivalencias por categoría o el producto por defecto de la empresa. Del
   producto salen la cuenta de gasto, los impuestos y la detracción.

Retención queda fuera de esta etapa: se avisa en la factura.
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "LGPL-3",
    "depends": [
        "l10n_pe_hr_expense_settlement",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/hr_expense_ic_product_views.xml",
        "views/account_move_views.xml",
        "views/hr_expense_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
