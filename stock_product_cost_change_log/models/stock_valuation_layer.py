from odoo import api, fields, models


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    standard_price = fields.Float(
        string="Cost",
        digits="Product Price",
        readonly=True,
    )
    kardex_cost_correction = fields.Boolean(
        string="Kardex Cost Correction",
        default=False,
        readonly=True,
        index="btree_not_null",
        help="Technical flag set on the manual layers created by the Kardex "
             "Cost Audit to align the recorded valuation with the chronological "
             "weighted average cost. These layers are part of the recorded "
             "valuation (and the inventory accounting) but are excluded from any "
             "WAC recomputation -- the cost audit and the legal valued kardex "
             "(SUNAT 13.1) -- so they do not double-count the very gap they "
             "close.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        layers = super().create(vals_list)
        layers._compute_and_store_standard_price()
        return layers

    def _compute_and_store_standard_price(self):
        for layer in self:
            standard_price = layer._get_resulting_standard_price()
            if standard_price is not None:
                self.env.cr.execute(
                    "UPDATE stock_valuation_layer SET standard_price = %s WHERE id = %s",
                    (standard_price, layer.id),
                )
        self.invalidate_recordset(["standard_price"])

    def _get_resulting_standard_price(self):
        self.ensure_one()
        product = self.product_id
        if product.lot_valuated and self.lot_id:
            return self.lot_id.standard_price
        else:
            return product.standard_price

    def _compute_weighted_avg_price(self, group_domain):
        aggregates = self._read_group(
            group_domain,
            groupby=[],
            aggregates=["value:sum", "quantity:sum"],
        )
        if aggregates:
            value_sum, quantity_sum = aggregates[0]
            if quantity_sum:
                return value_sum / quantity_sum
        return None

    def _get_inherited_price(self, domain):
        svl_data = self.search_read(
            domain, ["standard_price"], order="id desc", limit=1
        )
        return svl_data[0]["standard_price"] if svl_data else None

    def _apply_prices_to_groups(self, res, id_to_indices, price_map):
        for entity_id, indices in id_to_indices.items():
            price = price_map.get(entity_id)
            for idx in indices:
                if price is not None:
                    res[idx]["standard_price"] = price
                else:
                    res[idx].pop("standard_price", None)

    def _build_price_map(self, svl_data, id_field):
        price_map = {}
        for svl in svl_data:
            entity_id = svl[id_field][0] if svl.get(id_field) else None
            if entity_id and entity_id not in price_map:
                price_map[entity_id] = svl["standard_price"]
        return price_map

    @api.model
    def read_group(
        self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True
    ):
        res = super().read_group(
            domain,
            fields,
            groupby,
            offset=offset,
            limit=limit,
            orderby=orderby,
            lazy=lazy,
        )

        if not groupby or not res:
            return res

        base_field_names = {f.split(":")[0] for f in fields}
        if "standard_price" not in base_field_names:
            return res

        first_groupby = groupby[0] if isinstance(groupby, (list, tuple)) else groupby
        first_groupby_field = first_groupby.split(":")[0]

        has_product_or_lot_above = any(
            isinstance(item, (list, tuple))
            and len(item) == 3
            and item[0] in ("product_id", "lot_id")
            and item[1] == "="
            for item in domain
        )

        if first_groupby_field not in ("product_id", "lot_id"):
            if has_product_or_lot_above:
                price = self._get_inherited_price(domain)
                for group in res:
                    if price is not None:
                        group["standard_price"] = price
                    else:
                        group.pop("standard_price", None)
            else:
                for group in res:
                    group_domain = group.get("__domain", domain)
                    price = self._compute_weighted_avg_price(group_domain)
                    if price is not None:
                        group["standard_price"] = price
                    else:
                        group.pop("standard_price", None)
            return res

        if first_groupby_field == "lot_id":
            self._handle_lot_grouping(res, domain, has_product_or_lot_above)
        else:
            self._handle_product_grouping(res, domain, has_product_or_lot_above)

        return res

    def _handle_lot_grouping(self, res, domain, is_nested):
        lot_to_indices = {}
        none_indices = []

        for i, group in enumerate(res):
            lot_data = group.get("lot_id")
            if lot_data:
                lot_id = (
                    lot_data[0] if isinstance(lot_data, (list, tuple)) else lot_data
                )
                lot_to_indices.setdefault(lot_id, []).append(i)
            else:
                none_indices.append(i)

        if lot_to_indices:
            svl_data = self.search_read(
                domain + [("lot_id", "in", list(lot_to_indices.keys()))],
                ["lot_id", "standard_price"],
                order="id desc",
            )
            lot_price_map = self._build_price_map(svl_data, "lot_id")
            self._apply_prices_to_groups(res, lot_to_indices, lot_price_map)

        if none_indices:
            price = (
                self._get_inherited_price(domain + [("lot_id", "=", False)])
                if is_nested
                else None
            )
            for idx in none_indices:
                if price is not None:
                    res[idx]["standard_price"] = price
                else:
                    res[idx].pop("standard_price", None)

    def _handle_product_grouping(self, res, domain, is_nested):
        product_to_indices = {}

        for i, group in enumerate(res):
            product_data = group.get("product_id")
            if product_data:
                product_id = (
                    product_data[0]
                    if isinstance(product_data, (list, tuple))
                    else product_data
                )
                product_to_indices.setdefault(product_id, []).append(i)
            else:
                group.pop("standard_price", None)

        if not product_to_indices:
            return

        product_ids = list(product_to_indices.keys())

        if is_nested:
            lot_domain = next(
                (item for item in domain if item[0] == "lot_id" and item[1] == "="),
                None,
            )
            if lot_domain:
                base_domain = domain + [("product_id", "in", product_ids)]
                if lot_domain[2] is False:
                    base_domain.append(("lot_id", "=", False))

                svl_data = self.search_read(
                    base_domain, ["product_id", "standard_price"], order="id desc"
                )
                product_price_map = self._build_price_map(svl_data, "product_id")
                self._apply_prices_to_groups(
                    res, product_to_indices, product_price_map
                )
                return

        products = self.env["product.product"].browse(product_ids)
        lot_valuated_map = {p.id: p.lot_valuated for p in products}

        normal_ids = [pid for pid in product_ids if not lot_valuated_map.get(pid)]
        lot_valuated_ids = [pid for pid in product_ids if lot_valuated_map.get(pid)]

        if normal_ids:
            svl_data = self.search_read(
                domain + [("product_id", "in", normal_ids)],
                ["product_id", "standard_price"],
                order="id desc",
            )
            product_price_map = self._build_price_map(svl_data, "product_id")
            self._apply_prices_to_groups(
                res,
                {pid: product_to_indices[pid] for pid in normal_ids},
                product_price_map,
            )

        if lot_valuated_ids:
            aggregates = self._read_group(
                domain + [("product_id", "in", lot_valuated_ids)],
                groupby=["product_id"],
                aggregates=["value:sum", "quantity:sum"],
            )
            product_price_map = {
                product.id: value_sum / quantity_sum if quantity_sum else 0.0
                for product, value_sum, quantity_sum in aggregates
            }
            self._apply_prices_to_groups(
                res,
                {pid: product_to_indices[pid] for pid in lot_valuated_ids},
                product_price_map,
            )
