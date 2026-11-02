from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    operation_type_ids = fields.One2many(
        comodel_name="operation.type.sunat",
        inverse_name="picking_id",
        string="Tipos de Operaciones",
        help="Lista de tipos de operaciones relacionadas con este albarán.",
    )

    def add_operation_type(self):
        for record in self:
            # Validar si el tipo de operación SUNAT está definido
            if not record.type_operation_sunat:
                raise UserError(
                    "Debe definir el tipo de operación SUNAT para este documento."
                )

            # Validar si existen líneas en `move_ids_without_package`
            if not record.move_ids_without_package:
                raise UserError(
                    "No existen líneas en el documento para asignar el tipo de operación SUNAT."
                )

            # Asignar el tipo de operación a todas las líneas de `move_ids_without_package`
            record.move_ids_without_package.write(
                {"sunat_operation_type": record.type_operation_sunat}
            )

            # Eliminar registros existentes en `operation.type.sunat` asociados a este picking
            existing_operations = self.env["operation.type.sunat"].search(
                [("picking_id", "=", record.id)]
            )
            if existing_operations:
                existing_operations.unlink()

            # Crear nuevos registros en `operation.type.sunat` para cada línea de stock
            for line in record.move_ids_without_package:
                self.env["operation.type.sunat"].create(
                    {
                        "move_id": line.id,
                        "picking_id": record.id,
                    }
                )

            # Validación post-creación (opcional)
            if not self.env["operation.type.sunat"].search(
                [("picking_id", "=", record.id)]
            ):
                raise UserError(
                    "No se pudo crear ningún registro en 'operation.type.sunat'. Verifique las configuraciones."
                )
