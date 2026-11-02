# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Clases del PCGE cuyo detalle por producto no tiene sentido contable.
PRODUCT_DETAIL_FORBIDDEN_CLASSES = ("2",)


class AccountAccount(models.Model):
    _inherit = "account.account"

    closing_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de Cierre",
        ondelete="restrict",
        index="btree_not_null",
        domain="[('id', '!=', id), ('deprecated', '=', False)]",
        help=(
            "Cuenta usada como contrapartida al cerrar esta cuenta.\n"
            "Si se deja vacía, la cuenta NO se cierra.\n"
            "La cuenta destino puede tener a su vez otra cuenta de cierre: el "
            "asistente resolverá la cadena por niveles (p. ej. 60 -> 89 -> 59)."
        ),
    )

    closing_source_ids = fields.One2many(
        comodel_name="account.account",
        inverse_name="closing_account_id",
        string="Cuentas que cierran contra esta",
    )

    is_closing_account = fields.Boolean(
        string="Es Cuenta de Cierre/Resultado",
        compute="_compute_is_closing_account",
        store=True,
        readonly=False,
        help=(
            "Se marca automáticamente cuando otras cuentas la utilizan como "
            "contrapartida de cierre. Es informativo: lo que determina si una "
            "cuenta se cierra es tener una 'Cuenta de Cierre' configurada."
        ),
    )

    closing_depth = fields.Integer(
        string="Nivel de Cierre",
        compute="_compute_closing_depth",
        store=True,
        help=(
            "Número de saltos hasta el final de la cadena de cierre.\n"
            "Ejemplo: 60 -> 89 -> 59 da 60=2, 89=1, 59=0.\n"
            "El asistente procesa primero los niveles más altos, de modo que "
            "cada eslabón se cierre por separado y no se mezclen en un mismo asiento."
        ),
    )

    closing_detail = fields.Selection(
        selection=[
            ("none", "Sin detalle"),
            ("product", "Por producto"),
            ("partner", "Por contacto"),
        ],
        string="Detalle del Asiento de Cierre",
        default="none",
        required=True,
        help=(
            "Nivel de desglose de las líneas de cierre de esta cuenta.\n"
            "'Sin detalle': una línea por cuenta y moneda.\n"
            "'Por producto' / 'Por contacto': una línea por cada producto o "
            "contacto con saldo."
        ),
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("closing_source_ids")
    def _compute_is_closing_account(self):
        for account in self:
            account.is_closing_account = bool(account.closing_source_ids)

    @api.depends("closing_account_id", "closing_account_id.closing_depth")
    def _compute_closing_depth(self):
        """Profundidad de la cadena de cierre.

        Se recorre la cadena de forma iterativa (no recursiva) con un conjunto
        de visitados: así el compute nunca entra en bucle infinito aunque la
        configuración sea temporalmente inconsistente durante una importación,
        antes de que se dispare `_check_closing_account_recursion`.
        """
        for account in self:
            depth = 0
            visited = set()
            target = account.closing_account_id
            while target and target.id not in visited:
                visited.add(target.id)
                depth += 1
                target = target.closing_account_id
            account.closing_depth = depth

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("closing_account_id")
    def _check_closing_account_recursion(self):
        """Impide cadenas de cierre cíclicas (A -> B -> A)."""
        if self._has_cycle("closing_account_id"):
            raise ValidationError(
                _(
                    "La cadena de cuentas de cierre es recursiva. Revise la "
                    "configuración: una cuenta no puede cerrar, directa o "
                    "indirectamente, contra sí misma."
                )
            )

    @api.constrains("closing_account_id", "deprecated")
    def _check_closing_account_not_deprecated(self):
        for account in self.filtered("closing_account_id"):
            if account.closing_account_id.deprecated:
                raise ValidationError(
                    _(
                        "La cuenta de cierre %(target)s está obsoleta y no puede "
                        "usarse como contrapartida de %(source)s.",
                        target=account.closing_account_id.display_name,
                        source=account.display_name,
                    )
                )

    @api.constrains("closing_account_id", "company_ids")
    def _check_closing_account_company(self):
        for account in self.filtered("closing_account_id"):
            if not (account.company_ids & account.closing_account_id.company_ids):
                raise ValidationError(
                    _(
                        "La cuenta %(source)s y su cuenta de cierre %(target)s no "
                        "comparten ninguna compañía.",
                        source=account.display_name,
                        target=account.closing_account_id.display_name,
                    )
                )

    @api.constrains("closing_detail")
    def _check_closing_detail_product(self):
        """El detalle por producto no aplica a la clase 2 (existencias).

        `code` es dependiente de compañía en Odoo 18, por eso se evalúa con
        `with_company` para cada compañía de la cuenta.
        """
        for account in self.filtered(lambda a: a.closing_detail == "product"):
            for company in account.company_ids:
                code = account.with_company(company).code or ""
                if code.startswith(PRODUCT_DETAIL_FORBIDDEN_CLASSES):
                    raise ValidationError(
                        _(
                            "No puede activar el detalle por producto en cuentas "
                            "de la Clase 2 (%s).",
                            account.display_name,
                        )
                    )
