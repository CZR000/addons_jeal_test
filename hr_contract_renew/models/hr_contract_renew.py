# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from datetime import date, timedelta
from babel.dates import format_date
import logging

_logger = logging.getLogger(__name__)

# --- Estados del proceso de renovación ---
STATE_SELECTION = [
    ("draft", "Borrador"),
    ("generated", "Líneas Generadas"),
    ("processed", "Procesado"),
    ("cancel", "Cancelado"),
]

# --- Reglas para campos de solo lectura según el estado ---
READONLY_FIELD_STATES = {
    state: [("readonly", True)] for state in {"generated", "processed", "cancel"}
}


class HrContractRenew(models.Model):
    """
    Modelo que gestiona el proceso por lotes de renovación de contratos de empleados.
    Permite filtrar contratos por fecha de vencimiento, decidir cuáles renovar,
    y generar nuevos contratos automáticamente.
    """

    _name = "hr.contract.renew"
    _description = "Renovación de Contratos"
    _order = "id DESC"
    _rec_name = "name"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True

    # Nombre descriptivo basado en fechas (calculado automáticamente)
    name = fields.Char(
        string=_("Referencia"),
        copy=False,
        store=True,
        compute="_compute_name",
        index="trigram",
        help=_(
            "Nombre interno del proceso. Se genera automáticamente según las fechas."
        ),
    )

    # Código de secuencia única generado por ir.sequence
    sequence = fields.Char(
        string=_("Secuencia"),
        readonly=True,
        copy=False,
        default=lambda self: _("Nuevo"),
        index=True,
        help=_("Código único generado automáticamente para identificar el proceso."),
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string=_("Compañía"),
        required=True,
        readonly=True,
        states=READONLY_FIELD_STATES,
        default=lambda self: self.env.company,
        help=_("Compañía responsable del proceso de renovación."),
    )

    # --- Rango de fechas para filtrar contratos por vencimiento ---
    date_from = fields.Date(
        string=_("Fecha Desde"),
        required=True,
        states=READONLY_FIELD_STATES,
        default=fields.Date.context_today,
        help=_("Buscar contratos que finalicen a partir de esta fecha."),
    )

    date_to = fields.Date(
        string=_("Fecha Hasta"),
        required=True,
        states=READONLY_FIELD_STATES,
        default=fields.Date.context_today,
        help=_("Buscar contratos que finalicen hasta esta fecha."),
    )

    state = fields.Selection(
        selection=STATE_SELECTION,
        string=_("Estado"),
        required=True,
        copy=False,
        tracking=True,
        default="draft",
        help=_("Estado actual del proceso."),
    )

    renewal_line_ids = fields.One2many(
        comodel_name="hr.contract.renew.line",
        inverse_name="renewal_process_id",
        string="Líneas de Renovación",
        readonly=True,
        states={
            "generated": [("readonly", False)],
        },
        copy=False,
        help=_(
            "Líneas generadas automáticamente con los contratos que cumplen los "
            "criterios del proceso de renovación. Se pueden editar solo cuando "
            "el proceso está en estado 'Generado'."
        ),
    )

    # ---------------------------------------------------------------------------- #
    #                          TODO - METODOS CONSTRAINST                          #
    # ---------------------------------------------------------------------------- #
    @api.constrains("date_from", "date_to")
    def _check_date_range_coherence(self):
        """
        Verifica que la fecha 'date_from' no sea posterior a 'date_to'.

        Esta restricción asegura la coherencia del rango de fechas,
        evitando que la fecha final sea anterior a la inicial.
        """
        for record in self:
            if (
                record.date_from
                and record.date_to
                and record.date_to < record.date_from
            ):
                raise ValidationError(
                    _(
                        "La fecha 'Hasta' (%s) no puede ser anterior a la fecha 'Desde' (%s)."
                    )
                    % (record.date_to, record.date_from)
                )

    # ---------------------------------------------------------------------------- #
    #                             TODO - METODOS ACCION                            #
    # ---------------------------------------------------------------------------- #
    @api.model_create_multi
    def create(self, vals_list):
        """
        Asigna una secuencia única al crear nuevos registros.
        """
        for vals in vals_list:
            if vals.get("sequence", _("Nuevo")) == _("Nuevo"):
                vals["sequence"] = self.env["ir.sequence"].next_by_code(
                    "contract.renew.code"
                ) or _("Nuevo")
        return super().create(vals_list)

    def unlink(self):
        """
        Restringe la eliminación de procesos que no están en estado 'draft' o 'cancel'.

        - Evita eliminar registros en estado 'generated' o 'processed' para mantener
        la integridad del flujo de renovación.
        - Permite eliminar solo procesos que no hayan avanzado en el flujo.
        """
        # Estados restringidos
        restricted_states = {"generated", "processed"}
        # Filtrar registros bloqueados
        restricted_records = self.filtered(lambda r: r.state in restricted_states)

        if restricted_records:
            raise UserError(
                _(
                    "No puedes eliminar procesos en estado 'Generado' o 'Procesado'. "
                    "Primero cancela el proceso si deseas eliminarlo."
                )
            )

        return super().unlink()

    # ---------------------------------------------------------------------------- #
    #                              TODO - METODOS CRON                             #
    # ---------------------------------------------------------------------------- #
    @api.model
    def _cron_process_pending_renewals(self):
        """
        Acción programada para generar nuevos contratos en procesos de renovación aprobados.

        Flujo:
            1. Ejecuta diariamente mediante cron.
            2. Busca líneas de renovación que cumplan:
                - Proceso en estado 'processed'.
                - Línea marcada para renovar (to_renew=True).
                - Línea no completada (state != 'done').
                - Contrato original vence hoy o ya venció.
            3. Intenta crear un nuevo contrato en estado 'draft' para cada línea.
            4. Manejo de errores:
                - Rollback individual en caso de fallo.
                - Registro en chatter del proceso padre.
                - Confirmación (commit) tras cada registro para preservar trazabilidad.
            5. Mensaje resumen por cada proceso indicando cuántos contratos fueron renovados.

        Consideraciones:
            - Se confirma la transacción después de cada línea exitosa para evitar pérdida de progreso.
            - No se interrumpe la ejecución por errores en líneas individuales.
            - Se usan logs y mensajes en el chatter para trazabilidad completa.
        """
        _logger.info("Iniciando cron de renovación de contratos...")

        # Fecha objetivo: hoy
        target_date = date.today()

        # Buscar líneas pendientes en una sola consulta optimizada
        renewal_lines = self.env["hr.contract.renew.line"].search(
            [
                # Proceso aprobado
                ("renewal_process_id.state", "=", "processed"),
                # Marcadas para renovación
                ("to_renew", "=", True),
                # Vencidas o vencen hoy
                ("current_contract_id.date_end", "<=", target_date),
                # Sin contrato generado
                ("new_contract_id", "=", False),
            ]
        )

        if not renewal_lines:
            _logger.info("No hay contratos para renovar en la fecha de hoy.")
            return

        _logger.info(
            f"Se procesarán {len(renewal_lines)} líneas de renovación de contrato."
        )

        # Agrupar por proceso para manejo eficiente
        lines_by_process = {}
        for line in renewal_lines:
            lines_by_process.setdefault(line.renewal_process_id, []).append(line)

        # Iteración por proceso
        for process, lines in lines_by_process.items():
            success_count = 0

            for line in lines:
                try:
                    # Crear nuevo contrato
                    line._create_new_contract()
                    success_count += 1

                    # Confirmar transacción tras éxito
                    self.env.cr.commit()

                except Exception as e:
                    # Rollback ante error
                    self.env.cr.rollback()
                    error_message = _(
                        "Error al renovar el contrato del empleado <b>%s</b> (Línea ID %d): %s"
                    ) % (line.employee_id.name, line.id, str(e))

                    # Log del error
                    _logger.error(error_message)
                    process.message_post(body=error_message)

                    # Confirmar mensaje de error
                    self.env.cr.commit()

            # Mensaje resumen si hubo éxitos
            if success_count:
                process.message_post(
                    body=_(
                        "Se procesaron y crearon exitosamente <b>%d</b> renovaciones de contrato."
                    )
                    % success_count
                )
                self.env.cr.commit()

        _logger.info("Cron de renovación de contratos finalizado.")

    # ---------------------------------------------------------------------------- #
    #                             TODO - METODOS BUTTON                            #
    # ---------------------------------------------------------------------------- #
    def button_cancel(self):
        """
        Cancela el proceso de renovación y revierte cambios en contratos.

        Flujo:
            1. Restablece el estado de renovación de los contratos originales a 'No Evaluado' (none).
            2. Si existen nuevos contratos creados, los marca como cancelados (si no están cerrados).
            3. Actualiza el estado del proceso a 'cancel' y registra un mensaje en el chatter.
        """
        for process in self:
            # Restablecer contratos originales
            original_contracts = process.renewal_line_ids.mapped("current_contract_id")
            if original_contracts:
                original_contracts.write({"renewal_status": "none"})

            # Cancelar nuevos contratos creados (si aplica)
            new_contracts = process.renewal_line_ids.mapped("new_contract_id")
            if new_contracts:
                contracts_to_cancel = new_contracts.filtered(
                    lambda c: c.state not in ["close", "cancel"]
                )
                if contracts_to_cancel:
                    contracts_to_cancel.write({"state": "cancel"})

            # Cambiar estado del proceso
            process.write({"state": "cancel"})

            # Log en chatter
            process.message_post(
                body=_(
                    "El proceso fue cancelado. Se restablecieron los contratos originales y se cancelaron los contratos generados."
                )
            )

            # Actualizar el estado del registro a 'cancel'
            self.write({"state": "cancel"})

    def button_to_draft(self):
        """
        Regresa el proceso de renovación a estado 'draft' (borrador).

        Flujo:
            1. Restablecer el estado de renovación de los contratos originales a No Evaluado.
            2. Eliminar todas las líneas del proceso para asegurar consistencia.
            3. Cambiar el estado del proceso a 'draft'.
        """
        for process in self:
            # Obtener todos los contratos originales asociados
            contracts_to_reset = process.renewal_line_ids.mapped("current_contract_id")

            if contracts_to_reset:
                # Actualizamos el campo Selection con valor explícito 'none'
                contracts_to_reset.write({"renewal_status": "none"})

            # Eliminar líneas asociadas (sudo por seguridad en permisos)
            if process.renewal_line_ids:
                process.renewal_line_ids.sudo().unlink()

        # Cambiar estado del proceso
        self.write({"state": "draft"})

    def action_generate_renewal_lines(self):
        """
        Genera líneas de renovación de contratos para cada proceso en el conjunto de registros.

        Flujo:
            1. Valida que el proceso esté en estado 'draft'.
            2. Verifica que no existan líneas previas; si existen, solicita volver a borrador.
            3. Busca contratos activos, no evaluados, dentro del rango de fechas definido.
            4. Calcula nuevas fechas y prepara las líneas de renovación con datos por defecto.
            5. Crea las líneas en lote y actualiza el estado del proceso a 'generated'.

        Raises:
            UserError: Si el proceso no está en estado 'draft' o ya tiene líneas generadas.
        """
        # Itera sobre cada proceso de renovación seleccionado (puede ser 1 o varios registros)
        for renewal_process in self:
            # Si el estado no es 'draft', no se permite generar líneas
            if renewal_process.state != "draft":
                # Lanza un error para indicar que solo se puede ejecutar en borrador
                raise UserError(
                    _(
                        "Solo se pueden generar líneas cuando el proceso está en estado 'Borrador'."
                    )
                )

            # Si el registro ya tiene líneas de renovación asociadas, no se pueden regenerar
            if renewal_process.renewal_line_ids:
                # Lanza un error indicando que debe volver a borrador antes de regenerar
                raise UserError(
                    _(
                        "El proceso '%s' ya tiene líneas generadas. Regrese a borrador para regenerarlas."
                    )
                    % renewal_process.name
                )

            # Se buscan contratos activos, sin evaluación de renovación y con fecha dentro del rango del proceso
            domain = [
                # Contrato activo
                ("state", "=", "open"),
                # Sin evaluación previa
                ("renewal_status", "=", "none"),
                # Fecha fin >= inicio del rango
                ("date_end", ">=", renewal_process.date_from),
                # Fecha fin <= fin del rango
                ("date_end", "<=", renewal_process.date_to),
                # Misma compañía
                ("company_id", "=", renewal_process.company_id.id),
            ]

            # Ejecuta la búsqueda en el modelo hr.contract según el dominio
            contracts_to_renew = self.env["hr.contract"].search(domain)

            # Si no hay contratos encontrados
            if not contracts_to_renew:
                raise UserError(
                    _(
                        "No se encontraron contratos disponibles para renovar en el rango de fechas actual."
                    )
                )

            # Lista que almacenará los diccionarios con la información de cada línea a crear
            renewal_lines_data = []

            # Recorre cada contrato encontrado para preparar la información
            for contract in contracts_to_renew:
                # Calcula la duración del contrato original (diferencia entre fecha fin e inicio)
                contract_duration = relativedelta(
                    contract.date_end, contract.date_start
                )

                # Calcula la nueva fecha de inicio: un día después de que termina el contrato actual
                new_start_date = contract.date_end + timedelta(days=1)

                # Calcula la nueva fecha de fin: misma duración que el contrato original
                new_end_date = new_start_date + contract_duration

                # Añade un diccionario con los datos de la nueva línea de renovación
                renewal_lines_data.append(
                    {
                        # Relación al proceso actual
                        "renewal_process_id": renewal_process.id,
                        # Contrato actual
                        "current_contract_id": contract.id,
                        # Empleado asociado al contrato
                        "employee_id": contract.employee_id.id,
                        # Salario actual
                        "wage": contract.wage,
                        # Salario propuesto (por defecto igual al actual)
                        "new_wage": contract.wage,
                        # Nueva fecha de inicio
                        "new_date_from": new_start_date,
                        # Nueva fecha de fin
                        "new_date_to": new_end_date,
                    }
                )

            # Si se prepararon líneas, se crean en lote
            if renewal_lines_data:
                # Crea todas las líneas de renovación
                self.env["hr.contract.renew.line"].create(renewal_lines_data)
                # Actualiza los contratos a estado "pendiente de renovación"
                contracts_to_renew.write({"renewal_status": "pending_renew"})
                # Cambia el estado del proceso a 'generated'
                renewal_process.state = "generated"

    def action_approve_renewals(self):
        """
        Aprueba el proceso de renovación, asignando el estado correspondiente a cada contrato
        y actualizando el estado del proceso a 'processed'.

        Flujo:
            1. Solo procesa registros en estado 'generated'.
            2. Marca cada contrato original según la decisión de renovación:
                - 'to_renew' si la línea está seleccionada para renovar.
                - 'not_renew' en caso contrario.
            3. Publica un mensaje resumen en el chatter indicando el detalle de la aprobación.
            4. Cambia el estado del proceso a 'processed'.
        """
        # Filtrar procesos que se encuentran en estado 'generated'
        processes_to_approve = self.filtered(lambda p: p.state == "generated")

        # Si no hay procesos aptos, salir sin hacer nada
        if not processes_to_approve:
            return

        # Iterar sobre cada proceso que cumple la condición
        for process in processes_to_approve:

            # Obtener todas las líneas de renovación asociadas al proceso
            lines = process.renewal_line_ids

            # Si no hay líneas, continuar con el siguiente proceso
            if not lines:
                continue

            # Dividir líneas en dos grupos:
            # 1. Líneas seleccionadas para renovación (campo booleano to_renew = True)
            to_renew_lines = lines.filtered(lambda l: l.to_renew)
            # 2. Líneas que NO se renovarán
            not_renew_lines = lines - to_renew_lines

            # Actualización masiva de contratos
            # Si hay líneas que se van a renovar, actualizar contratos a 'to_renew'
            if to_renew_lines:
                # mapped obtiene todos los contratos relacionados para hacer una sola escritura
                to_renew_lines.mapped("current_contract_id").write(
                    {"renewal_status": "to_renew"}
                )

            # Si hay líneas que NO se renovarán, actualizar contratos a 'not_renew'
            if not_renew_lines:
                not_renew_lines.mapped("current_contract_id").write(
                    {"renewal_status": "not_renew"}
                )

            # Publicar mensaje en el chatter del proceso
            # Informar cuántos contratos se aprobaron para renovar y cuántos no
            process.message_post(
                body=_(
                    "Proceso aprobado: <b>%d</b> contratos marcados como 'A Renovar' "
                    "y <b>%d</b> contratos como 'No Renovar'."
                )
                % (len(to_renew_lines), len(not_renew_lines))
            )

        # --- Escritura única para optimizar rendimiento ---
        # Cambiar el estado de todos los procesos aprobados a 'processed'
        processes_to_approve.write({"state": "processed"})

    # ---------------------------------------------------------------------------- #
    #                            TODO - METODOS COMPUTE                            #
    # ---------------------------------------------------------------------------- #
    @api.depends("date_to", "date_from")
    def _compute_name(self):
        """
        Construye automáticamente el nombre del proceso de renovación en formato legible.

        Ejemplo:
            "Renovar contratos del 01 de enero al 25 de julio del 2025"

        Flujo:
            1. Si no hay fechas definidas, se asigna un texto genérico.
            2. Si hay fechas, se formatea la descripción con localización del idioma del usuario.

        Consideraciones:
            - Usar `babel` para aplicar el idioma definido en el contexto (lang).
            - Incluye el año solo una vez al final del rango.
        """
        # Obtener el código de idioma desde el contexto o el usuario
        lang_code = self.env.context.get("lang") or self.env.user.lang or "es_ES"

        for record in self:
            if not record.date_from or not record.date_to:
                # Nombre por defecto cuando no hay fechas definidas
                record.name = _("Nuevo Proceso de Renovación")
                continue

            # Formatear fecha de inicio y fin con nombres de mes completos (ej: "enero", "julio")
            start_str = format_date(
                record.date_from, format="d 'de' MMMM", locale=lang_code
            )
            end_str = format_date(
                record.date_to, format="d 'de' MMMM", locale=lang_code
            )
            year_str = record.date_to.strftime("%Y")

            # Construir el nombre con el formato requerido
            record.name = (
                f"Renovar contratos del {start_str} al {end_str} del {year_str}"
            )
