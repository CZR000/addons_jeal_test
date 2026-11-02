# -*- coding: utf-8 -*-
from odoo import models, fields, api
from lxml import etree
from copy import deepcopy


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # ─── CAMPO PRINCIPAL: Categoría de pérdida ───────────────────────────────
    x_loss_category = fields.Selection(
        selection=[
            ('price',       'Precio / Condiciones comerciales'),
            ('operations',  'Disponibilidad / Operaciones'),
            ('product',     'Producto / Especificaciones'),
            ('client',      'Cliente / Decisión'),
            ('commercial',  'Proceso Comercial'),
            ('service',     'Servicio / Postventa'),
            ('other',       'Otros'),
        ],
        string='Categoría de pérdida',
        tracking=True,
        copy=True,
    )

    # ─── CAMPOS DE DETALLE (uno por categoría) ────────────────────────────────
    x_loss_detail_price = fields.Selection(
        selection=[
            ('high_price',      'Precio elevado vs competencia'),
            ('bad_conditions',  'Condiciones comerciales no aceptadas'),
            ('no_credit',       'Sin crédito disponible'),
        ],
        string='Detalle Precio / Condiciones comerciales',
        tracking=True,
        copy=True,
    )

    x_loss_detail_operations = fields.Selection(
        selection=[
            ('no_stock',        'Sin stock disponible'),
            ('delivery_time',   'Tiempo de entrega no aceptado'),
            ('logistics',       'Problema logístico'),
        ],
        string='Detalle Disponibilidad / Operaciones',
        tracking=True,
        copy=True,
    )

    x_loss_detail_product = fields.Selection(
        selection=[
            ('no_spec',         'No cumple con la especificación técnica requerida'),
            ('brand',           'Marca no aceptada por el cliente'),
            ('quality',         'Calidad percibida inferior'),
        ],
        string='Detalle Producto / Especificaciones',
        tracking=True,
        copy=True,
    )

    x_loss_detail_client = fields.Selection(
        selection=[
            ('budget_cut',      'Recorte de presupuesto'),
            ('no_decision',     'No hubo decisión de compra'),
            ('internal_change', 'Cambio de responsable interno'),
        ],
        string='Detalle Cliente / Decisión',
        tracking=True,
        copy=True,
    )

    x_loss_detail_commercial = fields.Selection(
        selection=[
            ('late_quote',      'Cotización fuera de tiempo'),
            ('bad_follow',      'Mal seguimiento comercial'),
            ('competitor',      'Competidor con mejor propuesta'),
        ],
        string='Detalle Proceso Comercial',
        tracking=True,
        copy=True,
    )

    x_loss_detail_service = fields.Selection(
        selection=[
            ('bad_service',     'Mal servicio postventa previo'),
            ('no_support',      'Sin soporte técnico disponible'),
            ('warranty',        'Problemas con garantía'),
        ],
        string='Detalle Servicio / Postventa',
        tracking=True,
        copy=True,
    )

    x_loss_detail_other = fields.Selection(
        selection=[
            ('force_majeure',   'Fuerza mayor'),
            ('project_cancel',  'Proyecto cancelado'),
            ('other_reason',    'Otro motivo'),
        ],
        string='Detalle Otros',
        tracking=True,
        copy=True,
    )

    # ─── CAMPO CONSOLIDADO: computed, invisible en form, visible en lista ─────
    x_loss_detail_general = fields.Char(
        string='Detalle',
        compute='_compute_loss_detail_general',
        store=True,
        copy=True,
        readonly=True,
    )

    @api.depends(
        'x_loss_category',
        'x_loss_detail_price',
        'x_loss_detail_operations',
        'x_loss_detail_product',
        'x_loss_detail_client',
        'x_loss_detail_commercial',
        'x_loss_detail_service',
        'x_loss_detail_other',
    )
    def _compute_loss_detail_general(self):
        """
        Consolida en un solo campo Char el detalle correspondiente
        a la categoría seleccionada. Este campo es el que se muestra
        en la vista lista junto a x_loss_category.
        """
        # Mapeo campo → campo de detalle correspondiente
        detail_map = {
            'price':       'x_loss_detail_price',
            'operations':  'x_loss_detail_operations',
            'product':     'x_loss_detail_product',
            'client':      'x_loss_detail_client',
            'commercial':  'x_loss_detail_commercial',
            'service':     'x_loss_detail_service',
            'other':       'x_loss_detail_other',
        }

        for rec in self:
            category = rec.x_loss_category
            if not category:
                rec.x_loss_detail_general = False
                continue

            # Obtener el campo de detalle que corresponde a la categoría
            detail_field = detail_map.get(category)
            detail_value = rec[detail_field] if detail_field else False

            if not detail_value:
                rec.x_loss_detail_general = False
                continue

            # Obtener la etiqueta legible del valor de selección
            field_obj = rec._fields.get(detail_field)
            if field_obj:
                label = dict(field_obj.selection).get(detail_value, detail_value)
                rec.x_loss_detail_general = label
            else:
                rec.x_loss_detail_general = detail_value

    @api.model
    def _configure_loss_form_view(self):
        """Keep Studio positioning when present; allow clean Odoo 18 databases."""
        view = self.env.ref('crm_custom_fields.crm_lead_loss_fields_form')
        studio = self.env.ref(
            'studio_customization.odoo_studio_crm_lead_dd0d698a-3c65-4e35-bf29-693a91259456',
            raise_if_not_found=False,
        )
        if not studio:
            return
        parent_arch = studio._get_combined_arch()
        own_arch = etree.fromstring(view.arch_db)
        fields_to_add = own_arch.xpath(".//field[starts-with(@name, 'x_loss_')]")
        arch = etree.Element('data')
        for name in (
            'x_studio_categora_de_prdida', 'x_studio_detalle_precio',
            'x_studio_detalle_operaciones', 'x_studio_producto_especificaciones',
            'x_studio_cliente_decisin', 'x_studio_proceso_comercial',
            'x_studio_servicio_postventa', 'x_studio_otros',
        ):
            expression = "//field[@name='%s']" % name
            if parent_arch.xpath(expression):
                etree.SubElement(arch, 'xpath', expr=expression, position='replace')
        anchor = "//field[@name='x_studio_nmero_de_trabajadores']"
        if parent_arch.xpath(anchor):
            target = etree.SubElement(arch, 'xpath', expr=anchor, position='after')
        else:
            target = etree.SubElement(arch, 'xpath', expr='(//sheet/group)[1]', position='after')
            target = etree.SubElement(target, 'group', name='empiria_loss_details', string='Motivo de pérdida')
        for field in fields_to_add:
            target.append(deepcopy(field))
        view.write({'inherit_id': studio.id, 'arch_db': etree.tostring(arch, encoding='unicode')})
