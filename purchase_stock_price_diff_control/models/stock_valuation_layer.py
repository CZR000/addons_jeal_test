import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)

# Ajustes corregidos por ejecucion del cron de correccion historica.
CRON_BATCH = 300


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    pdiff_reversal_of_id = fields.Many2one(
        comodel_name="stock.valuation.layer",
        string="Reversión del ajuste",
        index="btree_not_null",
        copy=False,
        ondelete="set null",
        help="Capa de ajuste por diferencia de precio que esta capa revierte.",
    )
    pdiff_reversal_ids = fields.One2many(
        comodel_name="stock.valuation.layer",
        inverse_name="pdiff_reversal_of_id",
        string="Reversiones",
    )
    pdiff_expense_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Asiento de corrección en gasto",
        index="btree_not_null",
        copy=False,
        help="Asiento que devuelve al gasto la parte del ajuste que ya había "
        "salido de almacén cuando se corrigió.",
    )
    # NO almacenado a propósito: almacenarlo obligaría a Odoo a recalcularlo
    # fila por fila para todas las capas existentes durante la instalación,
    # leyendo además account.move.line (millones de filas en esta base). Eso
    # agotaba la memoria del worker y tumbaba la instalación. El dato es
    # derivable al vuelo y las búsquedas masivas van por SQL (ver más abajo).
    pdiff_is_adjustment = fields.Boolean(
        string="Es ajuste por diferencia de precio",
        compute="_compute_pdiff_is_adjustment",
        search="_search_pdiff_is_adjustment",
        help="Capa generada por la publicación de una factura de proveedor para "
        "corregir el costo de una capa de recepción.",
    )

    @api.depends("stock_valuation_layer_id", "account_move_line_id", "pdiff_reversal_of_id")
    def _compute_pdiff_is_adjustment(self):
        for layer in self:
            layer.pdiff_is_adjustment = bool(
                layer.stock_valuation_layer_id
                and layer.account_move_line_id
                and not layer.pdiff_reversal_of_id
            )

    def _search_pdiff_is_adjustment(self, operator, value):
        if operator not in ("=", "!="):
            raise NotImplementedError(operator)
        positive = (operator == "=") == bool(value)
        domain = [
            ("stock_valuation_layer_id", "!=", False),
            ("account_move_line_id", "!=", False),
            ("pdiff_reversal_of_id", "=", False),
        ]
        return domain if positive else ["!", *domain]

    # ------------------------------------------------------------------
    # Reversión de ajustes
    # ------------------------------------------------------------------

    def _pdiff_pending_adjustments(self):
        """Ajustes por diferencia de precio todavía vigentes (no revertidos)."""
        return self.filtered(
            lambda layer: layer.pdiff_is_adjustment and not layer.pdiff_reversal_ids
        )

    def _pdiff_on_hand_ratio(self):
        """Proporción de la capa de recepción que sigue en almacén.

        La parte ya consumida no puede devolverse al inventario: su exceso se
        llevó al gasto con la salida, así que la corrección tiene que volver por
        el mismo camino (ver ``_pdiff_prepare_expense_move_vals``).
        """
        self.ensure_one()
        parent = self.stock_valuation_layer_id
        if not parent or float_is_zero(
            parent.quantity, precision_rounding=parent.product_id.uom_id.rounding
        ):
            return 0.0
        return max(0.0, min(1.0, parent.remaining_qty / parent.quantity))

    def _pdiff_prepare_reversal_vals(self, description, value=None):
        """Valores de la capa compensatoria (importe en negativo)."""
        self.ensure_one()
        vals = {
            "company_id": self.company_id.id,
            "product_id": self.product_id.id,
            "quantity": 0.0,
            "unit_cost": 0.0,
            "remaining_qty": 0.0,
            "remaining_value": 0.0,
            "value": -self.value if value is None else value,
            "stock_valuation_layer_id": self.stock_valuation_layer_id.id,
            "account_move_line_id": self.account_move_line_id.id,
            "pdiff_reversal_of_id": self.id,
            "description": description,
        }
        if "price_diff_value" in self._fields:
            share = 1.0
            if value is not None and self.value:
                share = abs(value / self.value)
            vals["price_diff_value"] = -(self.price_diff_value or 0.0) * share
        if "lot_id" in self._fields:
            vals["lot_id"] = self.lot_id.id
        return vals

    def _pdiff_reverse_adjustments(self, description=None, force_date=None, stats=None):
        """Genera un ajuste negativo por cada ajuste previo vigente de ``self``.

        Devuelve las capas compensatorias creadas. El método es idempotente: un
        ajuste que ya tiene una reversión no se vuelve a revertir.

        :param force_date: fecha contable a forzar en los asientos de reversión.
            Necesario al corregir históricos cuyo periodo original está cerrado;
            sin ella, el core fecha el asiento con la fecha de la factura origen.
        """
        layers = self.sudo()._pdiff_pending_adjustments()
        vals_list = []
        sources = []
        parent_deltas = defaultdict(float)
        expense_amounts = {}
        for layer in layers:
            currency = layer.company_id.currency_id
            if currency.is_zero(layer.value):
                continue
            label = description or _(
                "Reversión de ajuste de precio (%(ref)s)",
                ref=layer.account_move_line_id.move_id.display_name or layer.id,
            )
            # Sólo puede devolverse al inventario la parte que sigue en almacén.
            ratio = layer._pdiff_on_hand_ratio()
            svl_value = currency.round(-layer.value * ratio)
            expense_value = currency.round(-layer.value - svl_value)

            vals_list.append(layer._pdiff_prepare_reversal_vals(label, value=svl_value))
            sources.append(layer)
            if not currency.is_zero(svl_value):
                parent_deltas[layer.stock_valuation_layer_id] += -svl_value
            if not currency.is_zero(expense_value):
                expense_amounts[len(vals_list) - 1] = (expense_value, label)
        if not vals_list:
            return self.browse()

        reversals = self.sudo().create(vals_list)
        # Devolver a la capa padre el valor que el ajuste previo le había sumado.
        for parent, delta in parent_deltas.items():
            parent.sudo().remaining_value -= delta

        entries = reversals
        if force_date:
            entries = reversals.with_context(force_period_date=force_date)
        entries._validate_accounting_entries()

        # La parte ya consumida se corrige contra el gasto, no contra el inventario.
        expense_map = {
            reversals[index]: amount for index, amount in expense_amounts.items()
        }
        if expense_map:
            failed = reversals._pdiff_post_expense_corrections(
                expense_map, force_date=force_date
            )
            if failed and stats is not None:
                stats["expense_failures"] = stats.get("expense_failures", 0) + len(failed)

        reversals._pdiff_sync_standard_price()
        return reversals

    def _pdiff_post_expense_corrections(self, expense_map, force_date=None):
        """Asiento que devuelve al gasto el exceso ya consumido.

        El ajuste duplicado cargó inventario contra la cuenta de existencias de
        compra, y la salida posterior llevó ese inventario al costo de ventas.
        Como el inventario ya está a cero, la corrección tiene que ir
        directamente entre la cuenta de compra y la de costo.
        """
        by_key = defaultdict(list)
        for reversal, (amount, label) in expense_map.items():
            product = reversal.product_id.with_company(reversal.company_id)
            accounts = product.product_tmpl_id.get_product_accounts()
            debit_account = accounts.get("stock_input")
            credit_account = accounts.get("stock_output") or accounts.get("expense")
            journal = accounts.get("stock_journal")
            if not (debit_account and credit_account and journal):
                _logger.warning(
                    "%s: sin cuentas de valorización para %s, no se corrige el "
                    "exceso ya consumido de %s.",
                    __name__, product.display_name, amount,
                )
                continue
            by_key[(reversal.company_id, journal)].append(
                (reversal, amount, label, debit_account, credit_account)
            )

        AccountMove = self.env["account.move"].sudo()
        failed = self.browse()
        for (company, journal), items in by_key.items():
            line_vals = []
            for reversal, amount, label, debit_account, credit_account in items:
                # Misma forma que las líneas de corrección de precio del core
                # (`_prepare_pdiff_aml_vals`): son costo de ventas y arrastran la
                # distribución analítica de la línea de factura de origen.
                analytic = reversal.account_move_line_id.analytic_distribution or False
                # `amount` ya viene en negativo: revierte el cargo original.
                for account, sign in ((credit_account, 1), (debit_account, -1)):
                    line_vals.append(
                        (0, 0, {
                            "name": label,
                            "account_id": account.id,
                            "product_id": reversal.product_id.id,
                            "balance": company.currency_id.round(amount * sign),
                            "analytic_distribution": analytic,
                            "display_type": "cogs",
                            "tax_ids": [],
                        })
                    )
            # Savepoint por asiento: una validación de un módulo de terceros no
            # puede tumbar la corrección de los demás lotes.
            try:
                with self.env.cr.savepoint():
                    move = AccountMove.with_company(company).create({
                        "journal_id": journal.id,
                        "move_type": "entry",
                        "company_id": company.id,
                        "date": force_date or fields.Date.context_today(self),
                        "ref": _("Corrección de ajuste de precio ya consumido"),
                        "line_ids": line_vals,
                    })
                    move._post(soft=False)
                for reversal, _amount, _label, _dbt, _crd in items:
                    reversal.pdiff_expense_move_id = move.id
            except Exception as error:  # noqa: BLE001
                failed |= self.browse([item[0].id for item in items])
                _logger.error(
                    "%s: no se pudo publicar la corrección al gasto de %s capas "
                    "en %s / %s: %s",
                    __name__, len(items), company.display_name, journal.name, error,
                )
        return failed

    def _pdiff_sync_standard_price(self):
        """Recalcula el costo del producto (y del lote) igual que hace el core."""
        layers = self.sudo()
        by_product = defaultdict(lambda: self.env["stock.valuation.layer"])
        by_lot = defaultdict(lambda: self.env["stock.valuation.layer"])
        for layer in layers:
            by_product[(layer.product_id, layer.company_id)] |= layer
            if "lot_id" in self._fields and layer.lot_id:
                by_lot[(layer.lot_id, layer.company_id)] |= layer

        for (product, company), _layers in by_product.items():
            product = product.with_company(company.id)
            if product.cost_method == "standard":
                continue
            if float_is_zero(product.quantity_svl, precision_rounding=product.uom_id.rounding):
                continue
            product.sudo().with_context(disable_auto_svl=True).write(
                {"standard_price": product.value_svl / product.quantity_svl}
            )

        for (lot, company), _layers in by_lot.items():
            lot = lot.with_company(company.id)
            if float_is_zero(lot.quantity_svl, precision_rounding=lot.product_id.uom_id.rounding):
                continue
            lot.sudo().with_context(disable_auto_svl=True).write(
                {"standard_price": lot.value_svl / lot.quantity_svl}
            )

    # ------------------------------------------------------------------
    # Detección de duplicados históricos
    # ------------------------------------------------------------------

    # La detección va en SQL a propósito. Hacerla con `search()` + `filtered()`
    # obliga a cargar en memoria todas las capas de ajuste y sus líneas de
    # factura asociadas; en esta base (148k capas, 1.9M apuntes) eso agota el
    # worker. Estas consultas se apoyan en los índices de stock_valuation_layer_id,
    # account_move_line_id y pdiff_reversal_of_id, y devuelven sólo ids.

    _PDIFF_BASE_WHERE = """
        svl.stock_valuation_layer_id IS NOT NULL
        AND svl.account_move_line_id IS NOT NULL
        AND svl.pdiff_reversal_of_id IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM stock_valuation_layer rev
             WHERE rev.pdiff_reversal_of_id = svl.id
        )
    """

    @api.model
    def _pdiff_extra_sql(self, company_ids=None, product_ids=None, date_from=None, date_to=None):
        """Filtros opcionales del asistente, como SQL parametrizado."""
        clauses, params = [], []
        if company_ids:
            clauses.append("svl.company_id IN %s")
            params.append(tuple(company_ids))
        if product_ids:
            clauses.append("svl.product_id IN %s")
            params.append(tuple(product_ids))
        if date_from:
            clauses.append("svl.create_date >= %s")
            params.append(date_from)
        if date_to:
            clauses.append("svl.create_date <= %s")
            params.append(date_to)
        return ("".join(" AND " + c for c in clauses), params)

    @api.model
    def _pdiff_find_duplicate_groups(self, limit=None, **filters):
        """Ajustes duplicados por re-publicación de la factura.

        Un duplicado es un conjunto de ajustes que comparten la misma capa de
        recepción y la misma línea de factura: sólo la última publicación es
        válida, las anteriores quedaron acumuladas.

        :return: lista de tuplas ``(id_a_conservar, [ids_sobrantes])``
        """
        extra, params = self._pdiff_extra_sql(**filters)
        query = """
            SELECT array_agg(svl.id ORDER BY svl.id) AS ids
              FROM stock_valuation_layer svl
             WHERE {base} {extra}
          GROUP BY svl.stock_valuation_layer_id, svl.account_move_line_id
            HAVING COUNT(*) > 1
          ORDER BY MIN(svl.id)
        """.format(base=self._PDIFF_BASE_WHERE, extra=extra)
        if limit:
            query += " LIMIT %s"
            params = params + [limit]
        self.env.cr.execute(query, params)
        return [(row[0][-1], row[0][:-1]) for row in self.env.cr.fetchall()]

    @api.model
    def _pdiff_find_unposted_adjustment_ids(self, limit=None, **filters):
        """Ajustes que siguen valorizando pese a que su factura ya no está publicada.

        Al cancelar (o dejar en borrador) una factura de proveedor, Odoo no
        retira el ajuste de precio que generó al publicarse, de modo que el
        inventario queda valorizado por un documento que ya no existe
        contablemente.
        """
        extra, params = self._pdiff_extra_sql(**filters)
        query = """
            SELECT svl.id
              FROM stock_valuation_layer svl
              JOIN account_move_line aml ON aml.id = svl.account_move_line_id
             WHERE {base} {extra}
               AND aml.parent_state IS DISTINCT FROM 'posted'
          ORDER BY svl.id
        """.format(base=self._PDIFF_BASE_WHERE, extra=extra)
        if limit:
            query += " LIMIT %s"
            params = params + [limit]
        self.env.cr.execute(query, params)
        return [row[0] for row in self.env.cr.fetchall()]

    @api.model
    def _pdiff_count_pending(self, **filters):
        """Cuántos ajustes erróneos quedan por corregir (sin cargarlos)."""
        extra, params = self._pdiff_extra_sql(**filters)
        query = """
            SELECT COALESCE(SUM(cnt - 1), 0)
              FROM (SELECT COUNT(*) AS cnt
                      FROM stock_valuation_layer svl
                     WHERE {base} {extra}
                  GROUP BY svl.stock_valuation_layer_id, svl.account_move_line_id
                    HAVING COUNT(*) > 1) g
        """.format(base=self._PDIFF_BASE_WHERE, extra=extra)
        self.env.cr.execute(query, params)
        duplicates = self.env.cr.fetchone()[0] or 0
        query = """
            SELECT COUNT(*)
              FROM stock_valuation_layer svl
              JOIN account_move_line aml ON aml.id = svl.account_move_line_id
             WHERE {base} {extra}
               AND aml.parent_state IS DISTINCT FROM 'posted'
        """.format(base=self._PDIFF_BASE_WHERE, extra=extra)
        self.env.cr.execute(query, params)
        return duplicates + (self.env.cr.fetchone()[0] or 0)

    @api.model
    def _pdiff_collect_bad_adjustments(self, limit=None, **filters):
        """Todos los ajustes erróneos vigentes: duplicados + facturas no publicadas.

        :return: ``(duplicate_groups, surplus_layers, unposted_layers)``
        """
        groups = self._pdiff_find_duplicate_groups(limit=limit, **filters)
        surplus_ids = [i for _keep, extra_ids in groups for i in extra_ids]
        remaining = None
        if limit:
            remaining = max(0, limit - len(surplus_ids))
        unposted_ids = []
        if remaining is None or remaining > 0:
            unposted_ids = self._pdiff_find_unposted_adjustment_ids(
                limit=remaining, **filters
            )
        surplus = self.browse(surplus_ids)
        unposted = self.browse(unposted_ids) - surplus
        return groups, surplus, unposted

    @api.model
    def _pdiff_cron_repair(self, batch=CRON_BATCH):
        """Corrige el histórico por lotes y se auto-desactiva al terminar.

        El ``post_init_hook`` activa este cron cuando hay demasiados ajustes que
        corregir para hacerlo dentro de la propia instalación. Así la instalación
        nunca se queda colgada y la corrección igualmente se completa sola.
        """
        summary = self.sudo()._pdiff_repair_all(limit=batch)
        # Segunda fase: donde anular y borrar son equivalentes, se borra, para no
        # dejar el par ajuste+reversión a la vista.
        remaining = max(0, batch - summary["layers_to_reverse"])
        if remaining:
            summary["layers_deleted"] = self.sudo()._pdiff_delete_safe_pairs(limit=remaining)
        if not self.sudo()._pdiff_count_pending() and not self.sudo()._pdiff_count_safe_deletable():
            cron = self.env.ref(
                "purchase_stock_price_diff_control.ir_cron_pdiff_repair",
                raise_if_not_found=False,
            )
            if cron:
                if self.env.context.get("ir_cron_progress_id"):
                    # The scheduler holds ir_cron locked in another cursor.
                    # Ask it to deactivate after this transaction completes.
                    cron._notify_progress(done=1, remaining=0, deactivate=True)
                else:
                    cron.sudo().active = False
            _logger.info(
                "%s: corrección histórica completada, cron desactivado.", __name__
            )
        return summary

    @api.model
    def action_pdiff_repair(self, limit=None, force_date=None):
        """Punto de entrada público para corregir el histórico (UI/RPC).

        ``limit`` permite procesar por lotes en llamadas sucesivas para no
        exceder el tiempo máximo de petición en bases grandes. Devuelve el
        resumen de lo corregido; cuando ``layers_to_reverse`` es 0 ya no queda
        nada pendiente.
        """
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(
                _("Necesita permisos de administrador contable para corregir la valorización.")
            )
        if force_date:
            force_date = fields.Date.to_date(force_date)
        summary = self.sudo()._pdiff_repair_all(force_date=force_date, limit=limit)
        remaining = max(0, (limit or 0) - summary["layers_to_reverse"]) if limit else None
        if remaining is None or remaining > 0:
            summary["layers_deleted"] = self.sudo()._pdiff_delete_safe_pairs(limit=remaining)
            summary["pending_delete"] = self.sudo()._pdiff_count_safe_deletable()
        return summary

    @api.model
    def _pdiff_repair_all(
        self, force_date=None, batch_size=200, commit=False, limit=None, **filters
    ):
        """Corrige el histórico de ajustes erróneos.

        Es la rutina que ejecuta el cron de corrección y también puede lanzarse
        a mano. Es idempotente: al volver a ejecutarla no encuentra nada que
        corregir. ``limit`` acota el trabajo de una pasada, de modo que en bases
        grandes nunca se monta una transacción inabarcable.

        :return: diccionario con el resumen de la corrección.
        """
        layer_model = self.sudo()
        groups, surplus, unposted = layer_model._pdiff_collect_bad_adjustments(
            limit=limit, **filters
        )
        to_reverse = surplus | unposted
        pending_total = layer_model._pdiff_count_pending(**filters)
        summary = {
            "duplicate_groups": len(groups),
            "duplicate_layers": len(surplus),
            "unposted_layers": len(unposted),
            "layers_to_reverse": len(to_reverse),
            "pending_total": pending_total,
            "value_reversed": 0.0,
            "products": len(to_reverse.product_id),
            "reversals_created": 0,
            "expense_failures": 0,
        }
        if not to_reverse:
            _logger.info("%s: no hay ajustes erróneos que corregir.", __name__)
            return summary

        force_date = force_date or fields.Date.context_today(layer_model)
        _logger.info(
            "%s: corrigiendo %s ajustes erróneos (%s duplicados en %s recepciones, "
            "%s de facturas no publicadas) por %s; productos: %s",
            __name__,
            summary["layers_to_reverse"],
            summary["duplicate_layers"],
            summary["duplicate_groups"],
            summary["unposted_layers"],
            round(sum(to_reverse.mapped("value")), 2),
            summary["products"],
        )

        created = 0
        value = 0.0
        for index in range(0, len(to_reverse), batch_size):
            batch = to_reverse[index:index + batch_size]
            reversals = batch._pdiff_reverse_adjustments(
                description=_("Corrección de ajuste de precio duplicado"),
                force_date=force_date,
                stats=summary,
            )
            created += len(reversals)
            value += sum(reversals.mapped("value"))
            if commit:
                self.env.cr.commit()  # pylint: disable=invalid-commit
            _logger.info(
                "%s: %s/%s ajustes corregidos",
                __name__,
                min(index + batch_size, len(to_reverse)),
                len(to_reverse),
            )
        summary["reversals_created"] = created
        summary["value_reversed"] = value
        _logger.info("%s: corrección finalizada: %s", __name__, summary)
        return summary

    # ------------------------------------------------------------------
    # Acción de servidor: eliminar valorización y regularizar asientos
    # ------------------------------------------------------------------

    def _pdiff_collect_deletable(self):
        """Separa lo seleccionado entre lo que se puede borrar y lo que no.

        Un ajuste sólo puede borrarse cuando la mercadería de su recepción sigue
        **íntegra en almacén**. Si ya salió, su exceso se trasladó al costo de
        ventas con la salida: borrar el ajuste quitaría el cargo al inventario
        sin tocar ese costo, y la cuenta de existencias quedaría descuadrada por
        ese importe. En esos casos la corrección tiene que quedar como asiento
        de anulación.

        Si se selecciona un ajuste, se arrastra su reversión (y viceversa), de
        modo que el par -que suma cero- desaparece entero.

        :return: ``(capas_a_borrar, bloqueadas)``
        """
        layers = self.sudo()
        candidates = layers | layers.pdiff_reversal_ids | layers.pdiff_reversal_of_id
        candidates = candidates.filtered(
            lambda layer: layer.stock_valuation_layer_id and layer.account_move_line_id
        )
        # En sudo: stock.valuation.layer no concede unlink a ningún grupo.
        deletable = layers.browse()
        blocked = layers.browse()
        for layer in candidates:
            source = layer.pdiff_reversal_of_id or layer
            if source.pdiff_reversal_ids.filtered("pdiff_expense_move_id"):
                # Se corrigió contra el gasto: la mercadería ya había salido.
                blocked |= layer
            elif float_is_zero(source._pdiff_on_hand_ratio() - 1.0, precision_digits=6):
                deletable |= layer
            else:
                blocked |= layer
        return deletable, blocked

    def action_pdiff_delete_valuation(self):
        """Elimina los ajustes seleccionados y regulariza sus asientos."""
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(
                _("Necesita permisos de administrador contable para eliminar valorización.")
            )
        deletable, blocked = self._pdiff_collect_deletable()
        if blocked:
            names = "\n".join(
                "• %s (S/ %s)" % (layer.product_id.display_name, layer.value)
                for layer in blocked[:8]
            )
            raise UserError(_(
                "No se puede eliminar la valorización de estas líneas porque la "
                "mercadería de su recepción ya salió del almacén:\n\n%(names)s\n\n"
                "Su exceso ya se trasladó al costo de ventas con la salida. Si se "
                "borrara el ajuste, la cuenta de existencias quedaría descuadrada "
                "por ese importe. En esos casos la corrección queda como asiento "
                "de anulación.", names=names))
        if not deletable:
            raise UserError(_(
                "Seleccione líneas de ajuste por diferencia de precio, que son las "
                "que corrigen el costo de una recepción."))
        deletable._pdiff_delete_layers()
        return True

    def _pdiff_delete_layers(self):
        """Borra las capas indicadas y sus asientos, dejando la valorización sana.

        No valida nada: quien llama es responsable de haber comprobado que
        borrarlas es equivalente a anularlas (ver ``_pdiff_collect_deletable``).
        """
        deletable = self.sudo()
        if not deletable:
            return deletable
        # Lo que estas capas sumaron a la capa de recepción hay que devolverlo.
        parent_deltas = defaultdict(float)
        for layer in deletable:
            parent_deltas[layer.stock_valuation_layer_id] += layer.value
        moves = deletable.account_move_id
        products = deletable.product_id
        companies = deletable.company_id

        deletable.unlink()
        for parent, delta in parent_deltas.items():
            if not float_is_zero(delta, precision_digits=2):
                parent.sudo().remaining_value -= delta

        # Los asientos de esas capas se quedan sin objeto: se eliminan.
        moves = moves.exists().sudo()
        if moves:
            moves.filtered(lambda move: move.state == "posted").button_draft()
            moves.unlink()

        for product in products:
            for company in companies:
                prod = product.with_company(company.id)
                if prod.cost_method == "standard":
                    continue
                if float_is_zero(prod.quantity_svl, precision_rounding=prod.uom_id.rounding):
                    continue
                prod.sudo().with_context(disable_auto_svl=True).write(
                    {"standard_price": prod.value_svl / prod.quantity_svl}
                )
        return deletable

    @api.model
    def _pdiff_find_safe_deletable_pairs(self, limit=None):
        """Pares ajuste+reversión que pueden borrarse sin descuadrar nada.

        Sólo los de recepciones que siguen **íntegras en almacén** y cuya
        corrección no tocó el gasto: ahí el par suma cero y borrarlo deja
        exactamente el mismo valor que dejarlo anulado, pero sin las dos líneas.
        """
        query = """
            SELECT rev.id, src.id
              FROM stock_valuation_layer rev
              JOIN stock_valuation_layer src ON src.id = rev.pdiff_reversal_of_id
              JOIN stock_valuation_layer par ON par.id = src.stock_valuation_layer_id
             WHERE rev.pdiff_reversal_of_id IS NOT NULL
               AND rev.pdiff_expense_move_id IS NULL
               AND par.quantity > 0
               AND par.remaining_qty = par.quantity
          ORDER BY rev.id
        """
        params = []
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        self.env.cr.execute(query, params)
        ids = []
        for rev_id, src_id in self.env.cr.fetchall():
            ids += [rev_id, src_id]
        return self.browse(ids)

    @api.model
    def _pdiff_count_safe_deletable(self):
        self.env.cr.execute("""
            SELECT COUNT(*)
              FROM stock_valuation_layer rev
              JOIN stock_valuation_layer src ON src.id = rev.pdiff_reversal_of_id
              JOIN stock_valuation_layer par ON par.id = src.stock_valuation_layer_id
             WHERE rev.pdiff_reversal_of_id IS NOT NULL
               AND rev.pdiff_expense_move_id IS NULL
               AND par.quantity > 0
               AND par.remaining_qty = par.quantity
        """)
        return self.env.cr.fetchone()[0] or 0

    @api.model
    def _pdiff_delete_safe_pairs(self, limit=None):
        """Borra los pares que pueden borrarse, para no dejar líneas de más."""
        layers = self.sudo()._pdiff_find_safe_deletable_pairs(limit=limit)
        if not layers:
            return 0
        _logger.info("%s: borrando %s capas (pares anulados en almacén)", __name__, len(layers))
        layers._pdiff_delete_layers()
        return len(layers)
