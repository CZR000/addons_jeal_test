from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from ..reports.report_valuation_inventory import LedgerReportExcel, LedgerReportTxt
from odoo.tools.float_utils import float_round
from datetime import datetime
from odoo.osv import expression
import base64
import pytz
import re


class PermanentInventoryValuation(models.Model):
    _name = "permanent.inventory.valuation"
    _description = "Inventario Permanente en Unidades físicas"
    _inherit = "ple.report.base"

    def _get_company_domain(self):
        return [("id", "in", [1, 7, 8, 9])]

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        domain=lambda self: self._get_company_domain(),
        default=lambda self: self.env.company,
    )

    validation_calc_balance = fields.Boolean(
        string="Saldo calculado",
    )

    validation_generate_report = fields.Boolean(
        string="Reporte generado",
    )

    xls_filename_valued = fields.Char(
        string="Nombre del archivo Excel valorizado",
    )

    xls_binary_valued = fields.Binary(
        string="Reporte Excel valorizado",
    )

    txt_filename_valued = fields.Char(
        string="Nombre del archivo TXT valorizado",
    )

    txt_binary_valued = fields.Binary(
        string="Reporte .TXT valorizado",
    )

    status_permanent = fields.Selection(
        [
            ("draft_perm", "Draft"),
            ("load_perm", "Open"),
            ("closed_perm", "Cancelled"),
        ],
        string="status permanent",
        default="draft_perm",
        readonly=True,
    )

    status_balance_final = fields.Selection(
        [
            ("draft_perm", "Draft"),
            ("load_perm", "Open"),
        ],
        string="status balanace final",
        default="draft_perm",
        readonly=True,
    )

    list_val_units = fields.One2many(
        string="Saldo Inicial",
        comodel_name="permanent.inventory.opening.balance",
        inverse_name="ple_stock_products",
    )

    list_val_unit_final = fields.One2many(
        string="Saldo Final",
        comodel_name="permanent.inventory.ending.balance",
        inverse_name="ple_stock_products_final",
    )

    # ---------------------------------------------------------------------------- #
    #                            DATA - GENERAR CONSULTA                           #
    # ---------------------------------------------------------------------------- #
    def action_generate_data(self):
        start_date = "%s 00:00:00" % self.date_start
        finish_date = "%s 23:59:59" % self.date_end

        query = """
                SELECT
                    stock_valuation_layer.id as stock_valuation,
                    product_product.id as product_id,
                    TO_CHAR (
                        coalesce(
                            account_move.date,
                            stock_valuation_layer.accounting_date
                        ),
                        'YYYYMM00'
                    ) as period,
                    CONCAT (
                        replace (account_move.name, '/', ''),
                        stock_valuation_layer.id
                    ) as cou,
                    coalesce(
                        (
                            SELECT
                                coalesce(account_move_line.ple_correlative, 'M000000001')
                            FROM
                                account_move
                                LEFT JOIN account_move_line ON account_move.id = account_move_line.move_id
                                LEFT JOIN account_account ON account_move_line.account_id = account_account.id
                            WHERE
                                (account_move_line.product_id = product_product.id)
                                AND (
                                    "account_move"."id" = stock_valuation_layer.account_move_id
                                )
                                AND (LEFT (account_account.code, 2) = '20')
                            LIMIT
                                1
                        ),
                        'M000000001'
                    ) as correlativo,
                    coalesce(
                        res_partner.annexed_establishment,
                        coalesce(
                            CASE
                                WHEN stock_location.usage = 'internal' THEN res_partner_orig.annexed_establishment
                                ELSE (
                                    CASE
                                        WHEN stock_location_dest.usage = 'internal' THEN res_partner_dest.annexed_establishment
                                        ELSE stock_establishment.annexed_establishment
                                    END
                                )
                            END,
                            ''
                        )
                    ) as establishment,
                    coalesce(product_template.stock_catalog, '') as catalog,
                    coalesce(product_template.stock_type, '') as stock_type,
                    coalesce(
                        LEFT (
                            replace (
                                replace (
                                    replace (product_product.default_code, '_', ''),
                                    '-',
                                    ''
                                ),
                                ' ',
                                ''
                            ),
                            24
                        ),
                        ''
                    ) as default_code,
                    coalesce(
                        CASE
                            WHEN product_template.unspsc_code_id > 0 THEN '1'
                            ELSE ''
                        END,
                        ''
                    ) as code_catag,
                    coalesce(product_unspsc_code.code, '') as unspsc_code,
                    TO_CHAR (
                        coalesce(
                            account_move.date,
                            stock_valuation_layer.accounting_date
                        ),
                        'DD/MM/YYYY'
                    ) as date_start,
                    CASE
                        WHEN stock_picking.picking_number != '' THEN '09'
                        ELSE COALESCE(l10n_latam_document_type.code, '00')
                    END as number_document,
                    CASE
                        WHEN stock_picking.picking_number != '' THEN LEFT (stock_picking.picking_number, 4)
                        ELSE COALESCE(
                            REGEXP_REPLACE (
                                stock_picking.serie_transfer_document,
                                '[^a-zA-Z0-9]',
                                '',
                                'g'
                            ),
                            '0'
                        )
                    END as serie_document,
                    CASE
                        WHEN stock_picking.picking_number != '' THEN SPLIT_PART (stock_picking.picking_number, '-', 2)
                        ELSE COALESCE(
                            REGEXP_REPLACE (
                                stock_picking.number_transfer_document,
                                '[^a-zA-Z0-9]',
                                '',
                                'g'
                            ),
                            '0'
                        )
                    END as reference_document,
                    CASE
                        WHEN stock_valuation_layer.sunat_operation_type is not null then stock_valuation_layer.sunat_operation_type
                        WHEN stock_move.picking_id > 0 then COALESCE(
                            COALESCE(stock_move.sunat_operation_type, stock_picking.type_operation_sunat, '99'),
                            stock_picking_type.ple_reason_id
                        )
                        WHEN stock_picking.origin LIKE '%retorno%' THEN COALESCE(
                            stock_picking_type.code,
                            stock_picking_type.ple_revert_id
                        )
                        ELSE COALESCE(
                            (
                                CASE
                                    WHEN stock_move.location_id > 0 then (
                                        case
                                            when stock_location_dest.usage = 'inventory' then '28'
                                            ELSE '99'
                                        end
                                    )
                                    ELSE '99'
                                END
                            ),
                            '99'
                        )
                    END as type_operation,
                    --coalesce(LEFT(pol.name,80), LEFT(product_template.name,80)) as description_prod,
                    --coalesce(LEFT(pol.name,80), LEFT(product_template.name,80)) as description,
                    LEFT (uom_uom.l10n_pe_edi_measure_unit_code, 3) as uom,
                    uom_uom.name as uom_name,
                    coalesce(
                        CASE
                            WHEN stock_valuation_layer.quantity > 0 THEN stock_valuation_layer.quantity
                            ELSE '0.00'
                        END,
                        '0.00'
                    ) as quantity_product_hand,
                    coalesce(
                        CASE
                            WHEN stock_valuation_layer.unit_cost > 0 THEN stock_valuation_layer.unit_cost
                            ELSE '0.00'
                        END,
                        '0.00'
                    ) as standard_price,
                    coalesce(
                        CASE
                            WHEN stock_valuation_layer.value > 0 THEN stock_valuation_layer.value
                            ELSE '0.00'
                        END,
                        '0.00'
                    ) as total_value,
                    coalesce(
                        CASE
                            WHEN stock_valuation_layer.quantity < 0 THEN stock_valuation_layer.quantity
                            ELSE '0.00'
                        END,
                        '0.00'
                    ) as quantity,
                    coalesce(
                        CASE
                            WHEN stock_valuation_layer.unit_cost < 0 THEN stock_valuation_layer.unit_cost
                            ELSE '0.00'
                        END,
                        '0.00'
                    ) as unit_cost,
                    coalesce(
                        CASE
                            WHEN stock_valuation_layer.value < 0 THEN stock_valuation_layer.value
                            ELSE '0.00'
                        END,
                        '0.00'
                    ) as value_cost
                FROM
                    stock_valuation_layer
                    LEFT JOIN   account_move                                ON  stock_valuation_layer.account_move_id       = account_move.id
                    LEFT JOIN   stock_move                                  ON  stock_valuation_layer.stock_move_id         = stock_move.id
                    LEFT JOIN   stock_warehouse                             ON  stock_move.warehouse_id                     = stock_warehouse.id
                    LEFT JOIN   res_partner                                 ON  stock_warehouse.partner_id                  = res_partner.id
                    LEFT JOIN   stock_location                              ON  stock_move.location_id                      = stock_location.id
                    LEFT JOIN   stock_warehouse as stock_warehouse_orig     ON  stock_location.storehouse_id                = stock_warehouse_orig.id
                    LEFT JOIN   res_partner as res_partner_orig             ON  stock_warehouse_orig.partner_id             = res_partner_orig.id
                    LEFT JOIN   stock_picking                               ON  stock_move.picking_id                       = stock_picking.id
                    LEFT JOIN   stock_picking_type                          ON  stock_picking.picking_type_id               = stock_picking_type.id
                    LEFT JOIN   product_product                             ON  stock_valuation_layer.product_id            = product_product.id
                    LEFT JOIN   product_template                            ON  product_product.product_tmpl_id             = product_template.id
                    LEFT JOIN   product_category                            ON  product_template.categ_id                   = product_category.id
                    LEFT JOIN   uom_uom                                     ON  product_template.uom_id                     = uom_uom.id
                    LEFT JOIN   product_unspsc_code                         ON  product_template.unspsc_code_id             = product_unspsc_code.id
                    LEFT JOIN   l10n_latam_document_type                    ON  stock_picking.transfer_document_type_id     = l10n_latam_document_type.id
                    LEFT JOIN   stock_location as stock_location_dest       ON  stock_move.location_dest_id                 = stock_location_dest.id
                    LEFT JOIN   stock_warehouse as stock_warehouse_dest     ON  stock_location_dest.storehouse_id           = stock_warehouse_dest.id
                    LEFT JOIN   res_partner as res_partner_dest             ON  stock_warehouse_dest.partner_id             = res_partner_dest.id
                    LEFT JOIN   res_company                                 ON  stock_valuation_layer.company_id            = res_company.id
                    LEFT JOIN   res_partner as stock_establishment          ON  res_company.partner_id                      = stock_establishment.id
                WHERE
                    (
                        "stock_valuation_layer"."accounting_date" >= '{start_date}'
                    )
                    AND (
                        "stock_valuation_layer"."accounting_date" <= '{end_date}'
                    )
                    AND ("product_template"."type" = 'product')
                    AND (stock_valuation_layer.company_id = '{company_id}')
                ORDER BY
                    product_id DESC,
                    "stock_valuation_layer"."create_date" ASC,
                    stock_valuation DESC;
            """.format(
            start_date=start_date,
            end_date=finish_date,
            company_id=self.company_id.id,
        )

        try:
            self.env.cr.execute(query)
            data_aml = self.env.cr.dictfetchall()
            return data_aml
        except Exception as error:
            raise ValidationError(
                f"Error al ejecutar la queries, comunicar al administrador: \n {error}"
            )

    # ---------------------------------------------------------------------------- #
    #                METODO - OBTENER PRODUCTOS DE SALDOS INICIALES                #
    # ---------------------------------------------------------------------------- #
    def opening_balances_id(self):
        products_id = []
        for datos in self.list_val_units:
            products_id.append(datos.product_id)

        return products_id

    # ---------------------------------------------------------------------------- #
    #                           METODO - SALDOS INICIALES                          #
    # ---------------------------------------------------------------------------- #
    def opening_balances(
        self, product_id, quantity_data, year, month, day, correct_name=False
    ):
        """
        Genera los datos del saldo inicial para un producto específico.
        """
        Product = self.env["product.product"]
        product = Product.browse(product_id)

        if not product.exists():
            raise UserError(f"Producto con ID {product_id} no encontrado.")

        # Buscar la primera capa de valoración de stock (si existe)
        valuation_layer = self.env["stock.valuation.layer"].search(
            [
                ("product_id", "=", product.id),
            ],
            order="id asc",
            limit=1,
        )

        # Datos de cantidad y valoración
        quantity_available = quantity_data.get("quantity_product_hand", 0.0)
        divisor = quantity_available if round(quantity_available, 2) != 0 else 1.0

        # Determinar categoría UNSPSC
        category_code = "1" if product.unspsc_code_id else ""

        # Extraer nombre limpio del producto
        if not correct_name:
            raw_name = product.display_name or ""
            correct_name = raw_name.split("]")[-1].strip()[:80]

        # Armar el diccionario de salida
        opening_data = {
            "period": f"{year}{month}00",
            "cou": f"SALDOINICIAL{year}{month}{product.id}{valuation_layer.id or 0}",
            "correlativo": "M000000001",
            "establishment": self.company_id.partner_id.annexed_establishment,
            "catalog": product.stock_catalog or "",
            "stock_type": product.stock_type or "",
            "default_code": re.sub(r"[^A-Za-z0-9]+", "", product.default_code or ""),
            "code_catag": category_code,
            "unspsc_code": product.unspsc_code_id.code or "",
            "date_start": f"{day}/{month}/{year}",
            "number_document": "00",
            "serie_document": "0",
            "reference_document": "0",
            "type_operation": "16",
            "description_prod": correct_name,
            "description": correct_name,
            "uom": quantity_data.get("udm_product"),
            "code_exist": quantity_data.get("code_exist"),
            "quantity_product_hand": quantity_available,
            "standard_price": quantity_data.get("standard_price"),
            "total_value": quantity_data.get("total_value"),
            "quantity": 0.00,
            "unit_cost": 0.00,
            "value_cost": 0.00,
            "quantity_hand_accumulated": round(quantity_available, 2),
            "cost_unit_accumulated": round(
                quantity_data.get("total_value", 0.0) / divisor, 2
            ),
            "cost_total_accumulated": round(quantity_data.get("total_value", 0.0), 2),
            "state": "1",
            "header": True,
        }

        return opening_data

    # ---------------------------------------------------------------------------- #
    #                      BOTON - GENERAR REPORTE VALORIZADO                      #
    # ---------------------------------------------------------------------------- #
    def action_generate_report_valued(self):
        self.validation_generate_report = True
        data_aml = self.action_generate_data()
        list_data = []
        hand_accumulated = 0
        total_accumulated = 0
        product_id = 0
        value_1 = 0.00
        value_2 = 0.00
        list_data_non = []

        start_date = self.date_start
        year, month, day = start_date.strftime("%Y/%m/%d").split("/")
        opening_balances = self.opening_balances_id()

        quantity_hand = dict()
        for datos in self.list_val_units:
            quantity_hand[datos.product_id] = {}
            quantity_hand[datos.product_id][
                "quantity_product_hand"
            ] = datos.quantity_product_hand
            quantity_hand[datos.product_id]["udm_product"] = datos.udm_product
            quantity_hand[datos.product_id]["standard_price"] = datos.standard_price
            quantity_hand[datos.product_id]["total_value"] = datos.total_value
            quantity_hand[datos.product_id]["code_exist"] = datos.code_exist

        env = self.env["product.product"]
        for obj_move_line in data_aml:
            header = True
            product = env.browse(obj_move_line.get("product_id"))
            display_name = product.display_name.split("]")[-1].strip()[:80]
            if obj_move_line.get("product_id") != product_id:
                hand_accumulated = 0
                total_accumulated = 0
                ids = obj_move_line.get("product_id")
                list_data_non.append(ids)
                if ids in opening_balances:
                    datos = self.opening_balances(
                        ids,
                        quantity_hand.get(ids),
                        year,
                        month,
                        day,
                        correct_name=display_name,
                    )

                    list_data.append(datos)
                    header = False
                    hand_accumulated = datos["quantity_hand_accumulated"]
                    total_accumulated = datos["cost_total_accumulated"]
                    opening_balances.remove(ids)

            else:
                header = False

            total_hand = (
                obj_move_line.get("quantity_product_hand", "")
                + obj_move_line.get("quantity", "0")
                + hand_accumulated
            )
            total_total = (
                obj_move_line.get("total_value", "")
                + obj_move_line.get("value_cost", "0")
                + total_accumulated
            )
            if round(total_hand, 2) == 0:
                divisor = 1
                total_total = 0
            else:
                divisor = total_hand

            if obj_move_line.get("total_value", "") > 0.00:
                value_1 = obj_move_line.get("standard_price", "")
                value_2 = 0.00
            else:
                value_1 = 0.00
                value_2 = obj_move_line.get("standard_price", "")

            property_cost_method = product.categ_id.property_cost_method
            code = ""
            if property_cost_method == "standard":
                code = "9"
            elif property_cost_method == "average":
                code = "1"
            elif property_cost_method == "fifo":
                code = "2"

            values = {
                "period": "%s%s00" % (year, month),
                "cou": obj_move_line.get("cou", ""),
                "correlativo": obj_move_line.get("correlativo", ""),
                "establishment": obj_move_line.get("establishment", ""),
                "catalog": obj_move_line.get("catalog", ""),
                "stock_type": obj_move_line.get("stock_type", ""),
                "default_code": obj_move_line.get("default_code", ""),
                "code_catag": obj_move_line.get("code_catag", ""),
                "unspsc_code": obj_move_line.get("unspsc_code", ""),
                "date_start": obj_move_line.get("date_start", ""),
                "number_document": obj_move_line.get("number_document", "00"),
                "serie_document": "".join(
                    filter(str.isalnum, obj_move_line.get("serie_document", "0"))
                )[:20],
                "reference_document": (
                    "".join(
                        filter(
                            str.isalnum, obj_move_line.get("reference_document", "0")
                        )
                    )
                ).zfill(8)[:20],
                "type_operation": obj_move_line.get("type_operation", ""),
                "description_prod": display_name,
                "description": display_name,
                "uom": obj_move_line.get("uom", ""),
                "code_exist": code,
                "quantity_product_hand": obj_move_line.get("quantity_product_hand", ""),
                "standard_price": value_1,
                "total_value": obj_move_line.get("total_value", ""),
                "quantity": obj_move_line.get("quantity", ""),
                "unit_cost": value_2,
                "value_cost": obj_move_line.get("value_cost", ""),
                "quantity_hand_accumulated": round(total_hand, 2),
                "cost_unit_accumulated": round((total_total / divisor), 2),
                "cost_total_accumulated": round(total_total, 2),
                "state": "1",
                "header": header,
            }
            product_id = obj_move_line.get("product_id")
            hand_accumulated = total_hand
            total_accumulated = total_total
            list_data.append(values)

        for datos_non in opening_balances:
            datos = self.opening_balances(
                datos_non,
                quantity_hand.get(datos_non),
                year,
                month,
                day,
                correct_name=False,
            )
            list_data.append(datos)

        ledger_report_xls = LedgerReportExcel(self, list_data)
        ledger_content_xls = ledger_report_xls.get_content()
        ledger_report = LedgerReportTxt(self, list_data)
        ledger_content = ledger_report.get_content()

        data = {
            "xls_binary_valued": base64.b64encode(ledger_content_xls),
            "xls_filename_valued": ledger_report_xls.get_filename(),
            "txt_binary_valued": base64.b64encode(
                ledger_content and ledger_content.encode() or "\n".encode()
            ),
            "txt_filename_valued": ledger_report.get_filename(),
            "status_permanent": "load_perm",
        }
        self.write(data)
        return True

    # ---------------------------------------------------------------------------- #
    #               BOTON - REGRESAR A BORRADOR EL REPORTE VALORIZADO              #
    # ---------------------------------------------------------------------------- #
    def action_rollback_permanent(self):
        self.write(
            {
                "xls_binary_valued": False,
                "xls_filename_valued": False,
                "txt_binary_valued": False,
                "txt_filename_valued": False,
                "status_permanent": "draft_perm",
            }
        )

    # ---------------------------------------------------------------------------- #
    #                        BOTON - CALCULAR SALDO INICIAL                        #
    # ---------------------------------------------------------------------------- #
    @api.depends("date_start")
    def action_calc_balance(self):
        self.validation_calc_balance = True
        start_date = self.date_start
        finish_date = datetime(start_date.year, start_date.month, start_date.day)
        datos = self.action_generate_product_list(finish_date)
        self.write({"list_val_units": [(5, 0, 0)]})
        for rec in datos.keys():
            res = datos.get(rec)
            if res["quantity_product_hand"] != 0.00:
                self.write(
                    {
                        "list_val_units": [
                            (
                                0,
                                0,
                                {
                                    "product_id": rec,
                                    "product_valuation": res["product_valuation"],
                                    "quantity_product_hand": res[
                                        "quantity_product_hand"
                                    ],
                                    "udm_product": res["udm_product"],
                                    "standard_price": res["standard_price"],
                                    "code_exist": res["code_exist"],
                                },
                            ),
                        ]
                    }
                )

    def action_generate_product_list(self, to_date):
        product = self.env["product.product"].search([("type", "=", "product")])
        domain_quant_loc, domain_move_in_loc, domain_move_out_loc = (
            product._get_domain_locations()
        )
        domain_quant = [("product_id", "in", product.ids)] + domain_quant_loc
        dates_in_the_past = False
        to_date = fields.Datetime.to_datetime(to_date)
        if to_date and to_date < fields.Datetime.now():
            dates_in_the_past = True

        domain_move_in = [("product_id", "in", product.ids)] + domain_move_in_loc
        domain_move_out = [("product_id", "in", product.ids)] + domain_move_out_loc

        if dates_in_the_past:
            domain_move_in_done = list(domain_move_in)
            domain_move_out_done = list(domain_move_out)
        if to_date:
            date_date_expected_domain_to = [("date", "<=", to_date)]
            domain_move_in += date_date_expected_domain_to
            domain_move_out += date_date_expected_domain_to

        Move = self.env["stock.move"].with_context(active_test=False)
        Quant = self.env["stock.quant"].with_context(active_test=False)
        domain_move_in_todo = [
            ("state", "in", ("waiting", "confirmed", "assigned", "partially_available"))
        ] + domain_move_in
        domain_move_out_todo = [
            ("state", "in", ("waiting", "confirmed", "assigned", "partially_available"))
        ] + domain_move_out
        moves_in_res = dict(
            (item["product_id"][0], item["product_qty"])
            for item in Move.read_group(
                domain_move_in_todo,
                ["product_id", "product_qty"],
                ["product_id"],
                orderby="id",
            )
        )
        moves_out_res = dict(
            (item["product_id"][0], item["product_qty"])
            for item in Move.read_group(
                domain_move_out_todo,
                ["product_id", "product_qty"],
                ["product_id"],
                orderby="id",
            )
        )
        quants_res = dict(
            (item["product_id"][0], (item["quantity"], item["reserved_quantity"]))
            for item in Quant.read_group(
                domain_quant,
                ["product_id", "quantity", "reserved_quantity"],
                ["product_id"],
                orderby="id",
            )
        )
        if dates_in_the_past:
            domain_move_in_done = [
                ("state", "=", "done"),
                ("date", ">", to_date),
            ] + domain_move_in_done
            domain_move_out_done = [
                ("state", "=", "done"),
                ("date", ">", to_date),
            ] + domain_move_out_done
            moves_in_res_past = dict(
                (item["product_id"][0], item["product_qty"])
                for item in Move.read_group(
                    domain_move_in_done,
                    ["product_id", "product_qty"],
                    ["product_id"],
                    orderby="id",
                )
            )
            moves_out_res_past = dict(
                (item["product_id"][0], item["product_qty"])
                for item in Move.read_group(
                    domain_move_out_done,
                    ["product_id", "product_qty"],
                    ["product_id"],
                    orderby="id",
                )
            )

        res = dict()
        for product in product.with_context(prefetch_fields=False):
            product_id = product.id
            if not product_id:
                res[product_id] = dict.fromkeys(
                    [
                        "product_valuation",
                        "quantity_product_hand",
                        "udm_product",
                        "standard_price",
                        "total_value",
                        "code_exist",
                    ],
                    0.0,
                )
                continue
            rounding = product.uom_id.rounding
            res[product_id] = {}
            if dates_in_the_past:
                qty_available = (
                    quants_res.get(product_id, [0.0])[0]
                    - moves_in_res_past.get(product_id, 0.0)
                    + moves_out_res_past.get(product_id, 0.0)
                )
            else:
                qty_available = quants_res.get(product_id, [0.0])[0]

            code = ""
            property_cost_method = product.categ_id.property_cost_method
            if property_cost_method == "standard":
                code = "9"
            elif property_cost_method == "average":
                code = "1"
            elif property_cost_method == "fifo":
                code = "2"

            res[product_id]["product_valuation"] = product.name
            res[product_id]["quantity_product_hand"] = float_round(
                qty_available, precision_rounding=rounding
            )
            res[product_id][
                "udm_product"
            ] = product.uom_id.l10n_pe_edi_measure_unit_code
            res[product_id]["standard_price"] = float_round(
                product.standard_price, precision_rounding=rounding
            )
            res[product_id]["code_exist"] = code

        return res

    # ---------------------------------------------------------------------------- #
    #                         BOTON - CALCULAR SALDO FINAL                         #
    # ---------------------------------------------------------------------------- #
    def calculate_products_final(self):
        balance_ending = self.generete_ending_balances()
        self.write(
            {
                "list_val_unit_final": [(5, 0, 0)],
            }
        )
        for rec in balance_ending.keys():
            res = balance_ending.get(rec)
            self.write(
                {
                    "list_val_unit_final": [
                        (
                            0,
                            0,
                            {
                                "product_id": rec,
                                "product_valuation": res["product_valuation"],
                                "quantity_product_hand": res["quantity_product_hand"],
                                "udm_product": res["udm_product"],
                                "standard_price": res["standard_price"],
                                "code_exist": res["code_exist"],
                            },
                        ),
                    ]
                }
            )

    def generete_ending_balances(self):
        data_aml = self.action_generate_data()
        hand_accumulated = 0
        total_accumulated = 0
        product_id = 0
        start_date = self.date_start
        year, month, day = start_date.strftime("%Y/%m/%d").split("/")
        opening_balances = self.opening_balances_id()
        ending_balances = dict()
        open_balance = list()
        quantity_hand = dict()

        for datos in self.list_val_units:
            open_balance.append(datos.product_id)
            quantity_hand[datos.product_id] = {}
            quantity_hand[datos.product_id][
                "quantity_product_hand"
            ] = datos.quantity_product_hand
            quantity_hand[datos.product_id][
                "product_valuation"
            ] = datos.product_valuation
            quantity_hand[datos.product_id]["udm_product"] = datos.udm_product
            quantity_hand[datos.product_id]["standard_price"] = datos.standard_price
            quantity_hand[datos.product_id]["total_value"] = datos.total_value
            quantity_hand[datos.product_id]["code_exist"] = datos.code_exist

        env = self.env["product.product"]
        for obj_move_line in data_aml:
            product = env.browse(obj_move_line.get("product_id"))
            display_name = product.display_name.split("]")[-1].strip()[:80]
            if obj_move_line.get("product_id") != product_id:

                if product_id != 0:
                    if product_id in open_balance:
                        open_balance.remove(product_id)
                    if hand_accumulated != 0:
                        ending_balances[product_id] = {}
                        ending_balances[product_id][
                            "product_valuation"
                        ] = product_valuation_final
                        ending_balances[product_id][
                            "quantity_product_hand"
                        ] = hand_accumulated
                        ending_balances[product_id]["udm_product"] = udm_product_final
                        ending_balances[product_id][
                            "standard_price"
                        ] = standar_price_final
                        ending_balances[product_id]["code_exist"] = code_final
                hand_accumulated = 0
                total_accumulated = 0
                ids = obj_move_line.get("product_id")

                if ids in opening_balances:
                    datos = self.opening_balances(
                        ids,
                        quantity_hand.get(ids),
                        year,
                        month,
                        day,
                        correct_name=display_name,
                    )
                    hand_accumulated = datos["quantity_hand_accumulated"]
                    total_accumulated = datos["cost_total_accumulated"]
                    opening_balances.remove(ids)

            total_hand = (
                obj_move_line.get("quantity_product_hand", "")
                + obj_move_line.get("quantity", "0")
                + hand_accumulated
            )
            total_total = (
                obj_move_line.get("total_value", "")
                + obj_move_line.get("value_cost", "0")
                + total_accumulated
            )

            if round(total_hand, 2) == 0:
                divisor = 1
            else:
                divisor = total_hand

            property_cost_method = product.categ_id.property_cost_method
            code = ""
            if property_cost_method == "standard":
                code = "9"
            elif property_cost_method == "average":
                code = "1"
            elif property_cost_method == "fifo":
                code = "2"

            product_valuation_final = display_name
            udm_product_final = obj_move_line.get("uom", "")
            standar_price_final = total_total / divisor
            code_final = code

            product_id = obj_move_line.get("product_id")
            hand_accumulated = total_hand
            total_accumulated = total_total

        if data_aml:
            if product_id in open_balance:
                open_balance.remove(product_id)

            if hand_accumulated != 0:
                ending_balances[product_id] = {}
                ending_balances[product_id][
                    "product_valuation"
                ] = product_valuation_final
                ending_balances[product_id]["quantity_product_hand"] = hand_accumulated
                ending_balances[product_id]["udm_product"] = udm_product_final
                ending_balances[product_id]["standard_price"] = standar_price_final
                ending_balances[product_id]["code_exist"] = code_final

        if open_balance:
            for rec in open_balance:
                product_id = rec
                datos = quantity_hand.get(product_id)
                ending_balances[product_id] = {}
                ending_balances[product_id]["product_valuation"] = datos[
                    "product_valuation"
                ]
                ending_balances[product_id]["quantity_product_hand"] = datos[
                    "quantity_product_hand"
                ]
                ending_balances[product_id]["udm_product"] = datos["udm_product"]
                ending_balances[product_id]["standard_price"] = datos["standard_price"]
                ending_balances[product_id]["code_exist"] = datos["code_exist"]

        return ending_balances

    # ---------------------------------------------------------------------------- #
    #                           BOTON - DECLARAR A SUNAT                           #
    # ---------------------------------------------------------------------------- #
    def action_close(self):
        super(PermanentInventoryValuation, self).action_close()

    # ---------------------------------------------------------------------------- #
    #                          BOTON - REGRESAR A BORRADOR                         #
    # ---------------------------------------------------------------------------- #
    def action_rollback(self):
        super(PermanentInventoryValuation, self).action_rollback()
        self.write(
            {
                "xls_filename": False,
                "xls_binary": False,
                "txt_binary": False,
                "txt_filename": False,
            }
        )
