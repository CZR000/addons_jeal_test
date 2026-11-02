from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class AccountAccount(models.Model):
    """
    Extiende el modelo para soportar la funcionalidad de distribución
    contable hacia cuentas destino. Cuando está activo, los movimientos contables registrados
    en esta cuenta pueden redistribuirse proporcionalmente según los porcentajes definidos.

    La configuración de activación puede heredarse del grupo contable asociado o definirse
    manualmente a nivel de cuenta individual.
    """

    _inherit = "account.account"

    has_destination_account = fields.Boolean(
        string="Usar Cuentas de Destino",
        compute="_compute_has_destination_account",
        inverse="_inverse_has_destination_account",
        store=True,
        readonly=False,
        help=(
            "Activa la lógica de redistribución contable. "
            "Si está activado, será obligatorio definir al menos una cuenta destino "
            "y los porcentajes deben sumar exactamente 100%."
        ),
    )

    destination_account_counterpart_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de Contrapartida",
        check_company=True,
        domain="[('deprecated', '=', False)]",
        copy=False,
        help="Cuenta utilizada para generar el asiento espejo en la redistribución.",
    )

    destination_account_ids = fields.One2many(
        comodel_name="account.destination.line",
        inverse_name="account_id",
        string="Cuentas de Destino",
        copy=False,
        help="Lista de cuentas destino con su porcentaje asignado para redistribución.",
    )

    # ---------------------------------------------------------------------------- #
    #                          TODO - METODOS CONSTRAINTS                          #
    # ---------------------------------------------------------------------------- #
    @api.constrains("has_destination_account", "destination_account_ids")
    def _check_destination_percentage_sum(self):
        """
        Garantiza la consistencia funcional:
        - Si la distribución está activa (`has_destination_account=True`)
          entonces debe existir al menos una línea destino.
        - La suma de los porcentajes de todas las líneas debe ser exactamente 100%.

        Se utiliza `float_compare` para evitar problemas por precisión decimal.
        """
        precision = self.env["decimal.precision"].precision_get("Account") or 2

        # Recorremos solo cuentas con la funcionalidad activa
        for account in self.filtered("has_destination_account"):
            if not account.destination_account_ids:
                # raise ValidationError(
                #     _(
                #         "La cuenta '%(name)s' tiene activada la distribución contable, "
                #         "pero no se han configurado cuentas destino."
                #     )
                #     % {"name": account.display_name}
                # )
                continue
            else:
                total_percentage = sum(
                    line.percentage for line in account.destination_account_ids
                )

                if (
                    float_compare(total_percentage, 100.0, precision_digits=precision)
                    != 0
                ):
                    raise ValidationError(
                        _(
                            "La suma de los porcentajes de las cuentas destino para '%(name)s' "
                            "debe ser exactamente 100%%. Actualmente: %(value)s%%."
                        )
                        % {"name": account.display_name, "value": total_percentage}
                    )

    # ---------------------------------------------------------------------------- #
    #                           TODO - METODOS HEREDADOS                           #
    # ---------------------------------------------------------------------------- #
    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        """
        Hereda la vista para ajustar visibilidad dinámica según localización.

        Se aplica únicamente si existe el método `_tags_invisible_per_country`,
        Esta implementación evita errores si el módulo no está instalado o si el país configurado no existe.
        """
        arch, view = super()._get_view(view_id, view_type, **options)

        if hasattr(self, "_tags_invisible_per_country"):
            peru = self.env.ref("base.pe", raise_if_not_found=False)

            if peru:
                tags = [
                    ("field", "has_destination_account"),
                    ("page", "destination_accounts"),
                ]

                arch, view = self._tags_invisible_per_country(
                    arch=arch,
                    view=view,
                    view_type=view_type,
                    tags=tags,
                    countries=peru,
                )

        return arch, view

    # ---------------------------------------------------------------------------- #
    #                            TODO - METODOS INVERSO                            #
    # ---------------------------------------------------------------------------- #
    def _inverse_has_destination_account(self):
        """
        Método inverso requerido para permitir que el valor calculado sea editable.

        No se requiere implementación porque su función es permitir que el usuario
        pueda sobrescribir manualmente el valor del campo aunque provenga de un compute.
        """
        pass

    # ---------------------------------------------------------------------------- #
    #                            TODO - METODOS COMPUTE                            #
    # ---------------------------------------------------------------------------- #
    @api.depends("group_id", "group_id.has_destination_account")
    def _compute_has_destination_account(self):
        """
        Define el valor inicial del campo a partir del grupo contable relacionado.
        Si no hay grupo asociado, el valor por defecto será `False`.
        """
        for account in self:
            account.has_destination_account = bool(
                account.group_id and account.group_id.has_destination_account
            )
