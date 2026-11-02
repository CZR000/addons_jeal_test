# -*- coding: utf-8 -*-
{
    "name": "Perú - Rendición de Gastos (Entregas a Rendir)",
    "version": "18.0.1.6.2",
    "category": "Human Resources/Expenses",
    "summary": "Comprobantes de gastos como facturas de proveedor reales (Registro "
               "de Compras) y liquidación contra los anticipos de la cuenta 14",
    "description": """
Rendición de gastos de empleados (Perú)
=======================================

Flujo: anticipo al empleado (cuenta 14) -> el empleado rinde sus comprobantes
en Gastos ("Pagado por: Empleado") -> cada comprobante genera una factura de
proveedor real -> desde la factura se liquida contra el anticipo.

1. Gasto: indicador "Va al Registro de Compras"; marcado, son obligatorios el
   proveedor real, el tipo de documento SUNAT, la serie y el número (se exigen
   en el formulario y al enviar el informe).
2. Informe de gastos: al aprobar se genera UNA factura de proveedor por
   comprobante, a nombre del proveedor real, en la moneda del comprobante, con
   serie-número en la referencia (lo que leen el PLE 8.1 y el SIRE). Los
   comprobantes que no van al Registro de Compras van al diario configurado
   (tipo compra, excluido del PLE y del SIRE, sin tipo de documento); los gastos
   sin comprobante de proveedor (p.ej. movilidad sin sustento) van ahí en una
   factura a nombre del empleado. Un comprobante no puede rendirse dos veces.
3. Liquidación contra el anticipo: al publicar la factura se liquida sola
   (o con el botón "Conciliar con Anticipo"): asiento 42 proveedor / 14
   empleado sin movimiento de caja, conciliando cada línea con su
   contrapartida. Siempre cancela el saldo completo; lo que no cubren los
   anticipos (del más antiguo al más reciente) queda a favor del empleado.
   Multimoneda: la diferencia de cambio la genera la conciliación nativa.
4. Empleado: centro de costos (distribución analítica) que se hereda en sus
   gastos.
5. Anticipos por moneda: un comprobante en dólares se aplica a los anticipos
   en dólares y uno en soles a los de soles; el informe puede fijar el
   anticipo o fondo que rinde (se ofrecen los de la moneda de sus
   comprobantes y se avisa si se elige uno de otra moneda). La liquidación usa el tipo de cambio de la
   factura (la 42 se cancela por su saldo exacto).
6. Cierre de la rendición desde el informe: categoría "Devolución de entrega
   a rendir" (genera el cobro en banco o caja conciliado con el anticipo; se
   avisa si una línea de gasto parece una devolución) y botón "Liquidar saldo"
   (pago o cobro del saldo pendiente de la 14).
7. Solicitudes de aprobación de anticipos: el pago va a la cuenta 14 de la
   moneda de la solicitud, desde el diario de esa moneda. Fondo de caja
   chica con cuenta y diario de liquidación propios y "Reponer fondo".
8. Solo se contabilizan informes aprobados.
9. Restablecer un informe contabilizado anula sus facturas y liquidaciones (el
   anticipo o el fondo recupera su saldo); en un periodo cerrado avisa.
10. Caja chica: cuenta propia del fondo (no cuenta como entrega a rendir),
    saldo total del fondo en el informe y en el empleado, y la solicitud de
    reposición nace con los aprobadores de la categoría (sin el propietario)
    y se abre desde el informe.

No instalar junto con hr_expense_cust ni hr_expense_extension: redefinen cómo
el informe de gastos arma las facturas (se duplicarían campos y facturas).
""",
    "author": "Empiria",
    "website": "https://www.empiria.com.pe",
    "license": "LGPL-3",
    "depends": [
        "hr_expense",
        "l10n_latam_invoice_document",
        "je_approval_expense_flow",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "wizard/hr_expense_settlement_wizard_views.xml",
        "views/account_move_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_expense_views.xml",
        "views/res_config_settings_views.xml",
        "views/approval_views.xml",
        "views/account_payment_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
