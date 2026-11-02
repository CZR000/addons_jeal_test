from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class AccountDestinationLine(models.Model):
    """
    Modelo que permite definir porcentajes de distribución para cuentas contables.

    Cada línea representa una regla que reparte un porcentaje desde una cuenta
    contable origen hacia una cuenta destino. La lógica de distribución será
    aplicada por otros módulos o automatismos.
    """

    _name = "account.destination.line"
    _description = "Línea de Distribución de Cuenta Contable"
    _rec_name = "destination_account_id"
    _order = "account_id, destination_account_id"
    _check_company_auto = True

    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta Origen",
        required=True,
        ondelete="cascade",
        index=True,
        help="Cuenta contable principal desde la cual se distribuirá el monto.",
    )

    destination_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de Destino",
        required=True,
        check_company=True,
        domain="[('deprecated', '=', False)]",
        help="Cuenta contable que recibirá un porcentaje del monto.",
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        readonly=True,
        index=True,
        default=lambda self: self.env.company,
    )

    percentage = fields.Float(
        string="Porcentaje",
        required=True,
        digits="Account",
        help="Porcentaje de monto que será asignado desde la cuenta origen hacia esta cuenta destino.",
    )

    # ---------------------------------------------------------------------------- #
    #                          TODO - METODOS CONSTRAINTS                          #
    # ---------------------------------------------------------------------------- #
    _sql_constraints = [
        (
            "unique_account_distribution_rule",
            "UNIQUE(account_id, destination_account_id, company_id)",
            _(
                "No se permiten líneas duplicadas con la misma Cuenta Origen, "
                "Cuenta Destino y Compañía."
            ),
        ),
    ]

    @api.constrains("percentage")
    def _check_percentage_valid_range(self):
        """
        Valida que el porcentaje ingresado esté dentro del rango permitido [0, 100].

        Utiliza float_compare con la precisión configurada para 'Account'
        para evitar errores típicos de comparación con valores flotantes.
        """
        # Obtener precisión definida en Odoo para cálculos contables
        precision = self.env["decimal.precision"].precision_get("Account") or 2

        for line in self:
            # Comparaciones seguras utilizando float_compare
            is_negative = (
                float_compare(line.percentage, 0.0, precision_digits=precision) < 0
            )
            is_exceeding_limit = (
                float_compare(line.percentage, 100.0, precision_digits=precision) > 0
            )

            if is_negative or is_exceeding_limit:
                raise ValidationError(
                    _(
                        "El porcentaje asignado a la cuenta de destino '%(account)s' "
                        "debe estar dentro del rango 0%% a 100%%.\n"
                        "Valor ingresado: %(value)s%%"
                    )
                    % {
                        "account": line.destination_account_id.display_name,
                        "value": line.percentage,
                    }
                )
