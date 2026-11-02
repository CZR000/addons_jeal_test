# -*- coding: utf-8 -*-
from . import models

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Se ejecuta una sola vez al instalar el módulo.
    Copia los datos de los campos Studio a los nuevos campos propios.

    Odoo 18: la firma de los post_init_hook cambió en v17 de
    ``(cr, registry)`` a ``(env,)``. Conservamos ``cr`` como alias local
    para no tocar el cuerpo SQL del hook original.
    """
    cr = env.cr
    _logger.info("CRM Loss Fields: Iniciando copia de datos desde campos Studio...")

    # ── Mapeo categoría Studio → key nuevo ────────────────────────────────────
    category_map = {
        'Perdidoo':                      'price',
        'Disponibilidad / Operaciones':  'operations',
        'Producto / Especificaciones':   'product',
        'Cliente / Decisión':            'client',
        'Proceso Comercial':             'commercial',
        'Servicio / Postventa':          'service',
        'Otros':                         'other',
    }

    detail_price_map = {
        'Precio elevado vs competencia':         'high_price',
        'Condiciones comerciales no aceptadas':  'bad_conditions',
        'Sin crédito disponible':                'no_credit',
    }
    detail_operations_map = {
        'Sin stock disponible':           'no_stock',
        'Tiempo de entrega no aceptado':  'delivery_time',
        'Problema logístico':             'logistics',
    }
    detail_product_map = {
        'Razón Producto':                                    'no_spec',
        'No cumple con la especificación técnica requerida': 'no_spec',
        'Marca no aceptada por el cliente':                  'brand',
        'Calidad percibida inferior':                        'quality',
    }
    detail_client_map = {
        'Recorte de presupuesto':        'budget_cut',
        'No hubo decisión de compra':    'no_decision',
        'Cambio de responsable interno': 'internal_change',
    }
    detail_commercial_map = {
        'Cotización fuera de tiempo':     'late_quote',
        'Mal seguimiento comercial':      'bad_follow',
        'Competidor con mejor propuesta': 'competitor',
    }
    detail_service_map = {
        'Mal servicio postventa previo':   'bad_service',
        'Sin soporte técnico disponible':  'no_support',
        'Problemas con garantía':          'warranty',
    }
    detail_other_map = {
        'Fuerza mayor':       'force_majeure',
        'Proyecto cancelado': 'project_cancel',
        'Otro motivo':        'other_reason',
    }

    cr.execute("""SELECT column_name FROM information_schema.columns
                  WHERE table_schema = current_schema() AND table_name = 'crm_lead'""")
    existing_columns = {row[0] for row in cr.fetchall()}

    # ── 1. Migrar categoría principal ─────────────────────────────────────────
    for studio_val, new_key in (category_map.items() if 'x_studio_categora_de_prdida' in existing_columns else []):
        cr.execute("""
            UPDATE crm_lead
               SET x_loss_category = %s
             WHERE x_studio_categora_de_prdida = %s
               AND (x_loss_category IS NULL OR x_loss_category = '')
        """, (new_key, studio_val))

    _logger.info("CRM Loss Fields: x_loss_category copiado.")

    # ── 2. Copiar campos de detalle ───────────────────────────────────────────
    detail_migrations = [
        ('x_studio_detalle_precio',            'x_loss_detail_price',      detail_price_map),
        ('x_studio_detalle_operaciones',       'x_loss_detail_operations', detail_operations_map),
        ('x_studio_producto_especificaciones', 'x_loss_detail_product',    detail_product_map),
        ('x_studio_cliente_decisin',           'x_loss_detail_client',     detail_client_map),
        ('x_studio_proceso_comercial',         'x_loss_detail_commercial', detail_commercial_map),
        ('x_studio_servicio_postventa',        'x_loss_detail_service',    detail_service_map),
        ('x_studio_otros',                     'x_loss_detail_other',      detail_other_map),
    ]

    for studio_field, new_field, value_map in detail_migrations:
        if studio_field not in existing_columns:
            continue
        for studio_val, new_key in value_map.items():
            cr.execute(f"""
                UPDATE crm_lead
                   SET {new_field} = %s
                 WHERE {studio_field} = %s
                   AND ({new_field} IS NULL OR {new_field} = '')
            """, (new_key, studio_val))
        _logger.info("CRM Loss Fields: %s copiado.", new_field)

    # ── 3. Calcular x_loss_detail_general ────────────────────────────────────
    cr.execute("""
        UPDATE crm_lead
           SET x_loss_detail_general = CASE
               WHEN x_loss_category = 'price' THEN
                   CASE x_loss_detail_price
                       WHEN 'high_price'     THEN 'Precio elevado vs competencia'
                       WHEN 'bad_conditions' THEN 'Condiciones comerciales no aceptadas'
                       WHEN 'no_credit'      THEN 'Sin crédito disponible'
                       ELSE x_loss_detail_price
                   END
               WHEN x_loss_category = 'operations' THEN
                   CASE x_loss_detail_operations
                       WHEN 'no_stock'      THEN 'Sin stock disponible'
                       WHEN 'delivery_time' THEN 'Tiempo de entrega no aceptado'
                       WHEN 'logistics'     THEN 'Problema logístico'
                       ELSE x_loss_detail_operations
                   END
               WHEN x_loss_category = 'product' THEN
                   CASE x_loss_detail_product
                       WHEN 'no_spec'  THEN 'No cumple con la especificación técnica requerida'
                       WHEN 'brand'    THEN 'Marca no aceptada por el cliente'
                       WHEN 'quality'  THEN 'Calidad percibida inferior'
                       ELSE x_loss_detail_product
                   END
               WHEN x_loss_category = 'client' THEN
                   CASE x_loss_detail_client
                       WHEN 'budget_cut'      THEN 'Recorte de presupuesto'
                       WHEN 'no_decision'     THEN 'No hubo decisión de compra'
                       WHEN 'internal_change' THEN 'Cambio de responsable interno'
                       ELSE x_loss_detail_client
                   END
               WHEN x_loss_category = 'commercial' THEN
                   CASE x_loss_detail_commercial
                       WHEN 'late_quote' THEN 'Cotización fuera de tiempo'
                       WHEN 'bad_follow' THEN 'Mal seguimiento comercial'
                       WHEN 'competitor' THEN 'Competidor con mejor propuesta'
                       ELSE x_loss_detail_commercial
                   END
               WHEN x_loss_category = 'service' THEN
                   CASE x_loss_detail_service
                       WHEN 'bad_service' THEN 'Mal servicio postventa previo'
                       WHEN 'no_support'  THEN 'Sin soporte técnico disponible'
                       WHEN 'warranty'    THEN 'Problemas con garantía'
                       ELSE x_loss_detail_service
                   END
               WHEN x_loss_category = 'other' THEN
                   CASE x_loss_detail_other
                       WHEN 'force_majeure'  THEN 'Fuerza mayor'
                       WHEN 'project_cancel' THEN 'Proyecto cancelado'
                       WHEN 'other_reason'   THEN 'Otro motivo'
                       ELSE x_loss_detail_other
                   END
               ELSE NULL
           END
         WHERE x_loss_category IS NOT NULL
    """)

    _logger.info("CRM Loss Fields: ✅ Copia de datos completada exitosamente.")
