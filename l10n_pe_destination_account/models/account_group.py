from odoo import _, api, fields, models


class AccountGroup(models.Model):
    """
    Extiende la logica para permitir que un grupo contable defina si sus cuentas
    deben utilizar distribución contable automática hacia cuentas destino.

    Si una cuenta pertenece a un grupo con esta opción habilitada, puede heredar
    automáticamente este comportamiento, evitando una configuración manual repetitiva.
    """

    _inherit = "account.group"

    has_destination_account = fields.Boolean(
        string="Usar Distribución Contable",
        help=_(
            "Si está activado, las cuentas asociadas a este grupo podrán aplicar "
            "distribución contable automática hacia cuentas destino."
        ),
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
                ]

                arch, view = self._tags_invisible_per_country(
                    arch=arch,
                    view=view,
                    view_type=view_type,
                    tags=tags,
                    countries=peru,
                )

        return arch, view
