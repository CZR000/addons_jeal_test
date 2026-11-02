# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    pass


#     """
#     Script de migración para eliminar metadatos y limpiar rastros
#     de los campos One2many eliminados en stock.picking.
#     """
#     # 1. Crear el entorno ORM
#     env = api.Environment(cr, SUPERUSER_ID, {})

#     # Archivar la vista
#     xml_id = "analytical_account_manager.stock_picking_form_inh"

#     try:
#         view_id = env["ir.model.data"]._xmlid_to_res_id(
#             xml_id, raise_if_not_found=False
#         )
#         if view_id:
#             view = env["ir.ui.view"].browse(view_id)
#             if view.active:
#                 view.write({"active": False})
#                 _logger.info(f"Vista archivada con éxito por XML ID: {xml_id}")
#     except Exception as e:
#         _logger.warning(f"No se pudo archivar la vista {xml_id}: {str(e)}")

#     # 2. Campos a eliminar
#     fields_to_remove = [
#         "stock_move_line_nosuggest_ids",
#         "stock_move_line_ids_without_package",
#     ]

#     # 2. Desvincular/Eliminar registros en ir.model.fields
#     model_name = "stock.picking"

#     # Buscamos los campos en el registro de Odoo
#     fields_records = env["ir.model.fields"].search(
#         [("model", "=", model_name), ("name", "in", fields_to_remove)]
#     )

#     if fields_records:
#         fields_records.unlink()

#     # 3. Eliminar datos huérfanos en ir.model.data (External IDs)
#     module_name = "analytical_account_manager"

#     # Buscamos si los campos tenían un ID externo registrado
#     external_ids = env["ir.model.data"].search(
#         [
#             ("module", "=", module_name),
#             ("model", "=", "ir.model.fields"),
#             ("name", "in", [f"field_stock_picking__{f}" for f in fields_to_remove]),
#         ]
#     )

#     if external_ids:
#         external_ids.unlink()
