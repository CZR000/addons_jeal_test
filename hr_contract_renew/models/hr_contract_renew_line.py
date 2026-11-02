# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrContractRenewLine(models.Model):
    """
    Modelo de línea de renovación de contrato.
    Representa una propuesta de renovación para un contrato específico,
    permitiendo definir nuevos términos como salario y fechas.
    """

    _name = "hr.contract.renew.line"
    _description = "Línea de Renovación de Contrato"
    _order = "employee_id"
    _check_company_auto = True

    # --- Relación principal con el proceso de renovación ---
    renewal_process_id = fields.Many2one(
        comodel_name="hr.contract.renew",
        string=_("Proceso de Renovación"),
        ondelete="cascade",
        required=True,
        index=True,
        copy=False,
        help=_("Proceso principal al que pertenece esta línea de renovación."),
    )

    # --- Compañía relacionada (heredada del proceso padre) ---
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="renewal_process_id.company_id",
        store=True,
        precompute=True,
        help=_("Compañía a la que pertenece este proceso."),
    )

    # --- Información del empleado y su contrato actual ---
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string=_("Empleado"),
        required=True,
        readonly=True,
        help=_("Empleado cuyo contrato se está evaluando para renovación."),
    )

    current_contract_id = fields.Many2one(
        comodel_name="hr.contract",
        string=_("Contrato Actual"),
        required=True,
        readonly=True,
        help=_("Contrato actual vigente del empleado."),
    )

    # --- Indicador de renovación ---
    to_renew = fields.Boolean(
        string=_("¿Renovar?"),
        default=True,
        help=_("Marcar si se desea renovar el contrato de este empleado."),
    )

    # --- Nuevas fechas para el contrato renovado ---
    new_date_from = fields.Date(
        string=_("Nueva Fecha de Inicio"),
        required=True,
        tracking=True,
        default=fields.Date.context_today,
        help=_("Fecha de inicio del nuevo contrato."),
    )

    new_date_to = fields.Date(
        string=_("Nueva Fecha de Fin"),
        required=True,
        tracking=True,
        default=fields.Date.context_today,
        help=_("Fecha de finalización del nuevo contrato."),
    )

    # --- Salario actual y nuevo ---
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
        string=_("Moneda"),
        store=True,
        precompute=True,
        help=_("Moneda utilizada para el salario."),
    )

    wage = fields.Monetary(
        string=_("Salario Actual"),
        required=True,
        tracking=True,
        readonly=True,
        default=0,
        currency_field="currency_id",
        help=_("Salario bruto mensual actual del contrato vigente."),
    )

    new_wage = fields.Monetary(
        string=_("Nuevo Salario"),
        required=True,
        tracking=True,
        currency_field="currency_id",
        help=_("Salario bruto mensual para el nuevo contrato."),
    )

    # --- Contrato nuevo (se llena tras generar la renovación) ---
    new_contract_id = fields.Many2one(
        comodel_name="hr.contract",
        string=_("Nuevo Contrato Generado"),
        readonly=True,
        copy=False,
        help=_("Contrato duplicado con los nuevos términos definidos en esta línea."),
    )

    # ---------------------------------------------------------------------------- #
    #                                TODO - METODOS                                #
    # ---------------------------------------------------------------------------- #
    def unlink(self):
        """
        Elimina la línea de renovación y actualiza el contrato original para indicar
        que vuelve a estar disponible para procesos de renovación.

        Flujo:
            1. Si existe un contrato asociado en la línea (campo current_contract_id),
               restablece su estado de renovación a 'none'.
            2. Llama al método `super()` para eliminar el registro de forma segura.
        """
        for line in self:
            # Obtener el contrato actual relacionado con la línea
            contract = line.current_contract_id

            # Si existe contrato, restablecer estado de renovación a 'none'
            if contract:
                contract.renewal_status = "none"

        # Ejecutar eliminación real mediante el método padre
        return super().unlink()

    def _create_new_contract(self):
        """
        Crea un nuevo contrato a partir de la línea de renovación actual.

        Flujo:
            1. Verifica que existan las fechas de inicio y fin (nuevas).
            2. Duplica el contrato original aplicando valores personalizados (fechas, salario, nombre).
            3. Configura el nuevo contrato en estado 'draft' (borrador) inicialmente.
            4. Añade trazabilidad en el chatter del contrato original y del nuevo contrato.
            5. Actualiza la línea para vincularla al nuevo contrato.

        Consideraciones:
            - Usa `ensure_one()` para evitar múltiples registros.
            - Usa `copy(default=...)` para duplicar el contrato aplicando modificaciones.
            - El nuevo contrato no se marca como `renewal_status` porque ya está renovado.

        :return: El nuevo contrato creado.
        :rtype: hr.contract (recordset)
        """
        # Asegura que el método se ejecute sobre un único registro
        self.ensure_one()

        # Si no se definieron las nuevas fechas, lanzar error
        if not self.new_date_from or not self.new_date_to:
            raise ValidationError(
                _(
                    "Las fechas de inicio y fin deben estar definidas para generar el nuevo contrato del empleado %s."
                )
                % self.employee_id.name
            )

        # Si ya existe un nuevo contrato vinculado, no hacer nada
        if self.new_contract_id:
            return self.new_contract_id

        # Preparación de valores para el nuevo contrato
        new_values = {
            # Nueva fecha de inicio
            "date_start": self.new_date_from,
            # Nueva fecha de fin
            "date_end": self.new_date_to,
            # Nuevo salario
            "wage": self.new_wage,
            "name": _("Renovación de Contrato para %s (%s)")
            % (
                self.employee_id.name,
                self.new_date_from.year,
            ),
            # Estado inicial en borrador
            "state": "draft",
            # Evitar que aparezca como pendiente
            "renewal_status": "none",
        }

        # Duplicar el contrato original aplicando los cambios definidos en new_values
        new_contract = self.current_contract_id.copy(default=new_values)

        # Cambia a estado en curso
        new_contract.state = "open"

        # Mensaje en el nuevo contrato indicando su origen
        new_contract.message_post(
            body=_(
                "Este contrato fue generado automáticamente por el proceso de renovación <b>%s</b>."
            )
            % self.renewal_process_id.display_name
        )

        # Mensaje en el contrato original indicando que fue renovado
        self.current_contract_id.message_post(
            body=_("Este contrato ha sido renovado. El nuevo contrato es <b>%s</b>.")
            % new_contract.display_name
        )

        # Vincular la línea con el nuevo contrato creado
        self.write(
            {
                "new_contract_id": new_contract.id,
            }
        )

        return new_contract
