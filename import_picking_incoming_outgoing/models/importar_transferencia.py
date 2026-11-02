# -*- coding: utf-8 -*-

import base64
import xlrd
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging
_logger = logging.getLogger(__name__)


class ImportarTransferencia(models.TransientModel):
    _name = "picking.incoming.outgoing"
    _description = 'Asistente para Importar Transferencias de Inventario'

    # -------------------------------------------------------------------------
    # CAMPOS DEL ASISTENTE
    # -------------------------------------------------------------------------
    archivo = fields.Binary(
        string="Archivo Excel de Importación",
        required=True,
    )

    nombre_archivo = fields.Char(
        string='Nombre del Archivo',
    )

    company_id = fields.Many2one(
        'res.company',
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
    )

    tipo_operacion_id = fields.Many2one(
        'stock.picking.type',
        string='Tipo de Operación',
        required=True,
        check_company=True,
    )

    estado = fields.Selection(
        selection=[
            ('confirmed', 'Confirmado (Listo para procesar)'),
            ('done', 'Validado (Transferencia completada)'),
        ],
        default='confirmed',
        string='Estado Final',
        required=True,
        help="Confirmado: crea el picking listo para procesar. "
             "Validado: además ejecuta la transferencia completa.",
    )

    ubicacion_origen_id = fields.Many2one(
        'stock.location',
        string="Ubicación de Origen",
        required=True,
        check_company=True,
    )

    ubicacion_destino_id = fields.Many2one(
        'stock.location',
        string="Ubicación de Destino",
        required=True,
        check_company=True,
    )

    importar_producto_por = fields.Selection(
        selection=[
            ('name', 'Nombre'),
            ('code', 'Referencia Interna (Código)'),
            ('barcode', 'Código de Barras'),
        ],
        string='Importar Producto Usando',
        default='code',
        required=True,
    )

    # -------------------------------------------------------------------------
    # ONCHANGES: Filtrar por compañía y autocompletar ubicaciones
    # -------------------------------------------------------------------------
    @api.onchange('tipo_operacion_id')
    def _onchange_tipo_operacion_id(self):
        """Al seleccionar tipo de operación, llenar ubicaciones automáticamente."""
        if self.tipo_operacion_id:
            if self.tipo_operacion_id.default_location_src_id:
                self.ubicacion_origen_id = self.tipo_operacion_id.default_location_src_id
            if self.tipo_operacion_id.default_location_dest_id:
                self.ubicacion_destino_id = self.tipo_operacion_id.default_location_dest_id

    # -------------------------------------------------------------------------
    # MAPEO FLEXIBLE DE ENCABEZADOS
    # -------------------------------------------------------------------------
    MAPEO_ENCABEZADOS = {
        # --- ID del Picking ---
        'id del picking': 'picking_id',
        'picking id': 'picking_id',
        'id picking': 'picking_id',
        'picking': 'picking_id',
        # --- Contacto (Proveedor / Cliente / Partner) — por nombre ---
        'proveedor': 'contacto',
        'cliente': 'contacto',
        'contacto': 'contacto',
        'partner': 'contacto',
        'vendor': 'contacto',
        'customer': 'contacto',
        # --- RUC de Contacto (Proveedor / Cliente / Partner) ---
        'ruc contacto': 'ruc_contacto',
        'ruc de contacto': 'ruc_contacto',
        'ruc proveedor': 'ruc_contacto',
        'ruc de proveedor': 'ruc_contacto',
        'ruc cliente': 'ruc_contacto',
        'ruc de cliente': 'ruc_contacto',
        'vat': 'ruc_contacto',
        # --- Documento Origen ---
        'documento origen': 'origen',
        'documento de origen': 'origen',
        'source document': 'origen',
        'origen': 'origen',
        'source': 'origen',
        # --- Propietario — por nombre ---
        'propietario': 'propietario',
        'owner': 'propietario',
        # --- RUC del Propietario ---
        'ruc propietario': 'ruc_propietario',
        'ruc de propietario': 'ruc_propietario',
        'ruc del propietario': 'ruc_propietario',
        # --- Política de Envío ---
        'politica de envio': 'politica_envio',
        u'pol\xedtica de env\xedo': 'politica_envio',
        'shipping policy': 'politica_envio',
        # --- Producto ---
        'producto': 'producto',
        'product': 'producto',
        # --- Descripción ---
        'descripcion': 'descripcion',
        u'descripci\xf3n': 'descripcion',
        'description': 'descripcion',
        # --- Demanda Inicial / Cantidad ---
        'demanda inicial': 'cantidad',
        'demanda': 'cantidad',
        'cantidad': 'cantidad',
        'initial demand': 'cantidad',
        'quantity': 'cantidad',
        'qty': 'cantidad',
        u'demanda inicial (peso neto)': 'cantidad',
        'demanda inicial (peso neto)': 'cantidad',
        # --- Seguimiento (Tracking) ---
        'seguimiento': 'seguimiento',
        'tracking': 'seguimiento',
        'trazabilidad': 'seguimiento',
        # --- Lote ---
        'lote': 'lote',
        'lot': 'lote',
        # --- Número de Serie (trazabilidad por serial) ---
        'numero de serie': 'serie',
        u'n\xfamero de serie': 'serie',
        'serial number': 'serie',
        'serial': 'serie',
        # --- Ticket de Pesaje ---
        'ticket de pesaje': 'ticket_pesaje',
        'ticket pesaje': 'ticket_pesaje',
        # --- Fecha (informativa, se ignora por ahora) ---
        'fecha': 'fecha_ticket',
        # --- Transportista — por nombre ---
        'transportistas': 'transportista',
        'transportista': 'transportista',
        # --- RUC del Transportista ---
        'ruc transportista': 'ruc_transportista',
        'ruc de transportista': 'ruc_transportista',
        'ruc transportistas': 'ruc_transportista',
        'ruc de transportistas': 'ruc_transportista',
        'ruc del transportista': 'ruc_transportista',
        # --- Guías GRR ---
        'guias grr': 'guias_grr',
        'guia grr': 'guias_grr',
        'grr': 'guias_grr',
        # --- Guías GRT ---
        'guias grt': 'guias_gtr',
        'guia grt': 'guias_gtr',
        'grt': 'guias_gtr',
        # --- Placa ---
        'placa': 'placa',
        # --- Tipo de Transporte ---
        'tipo de transporte': 'tipo_transporte',
        'tipo transporte': 'tipo_transporte',
        'transport type': 'tipo_transporte',
        # --- Tipo Documento de Traslado ---
        'tipo de documento de traslado': 'tipo_doc_traslado',
        'tipo doc traslado': 'tipo_doc_traslado',
        'tipo doc. traslado': 'tipo_doc_traslado',
        'tipo de docuemnto de traslado': 'tipo_doc_traslado',
        'tipo docuemnto de traslado': 'tipo_doc_traslado',
        # --- Serie Documento de Traslado ---
        'serie doc traslado': 'serie_traslado',
        'serie traslado': 'serie_traslado',
        'serie doc. traslado': 'serie_traslado',
        # --- Número Documento de Traslado ---
        'numero de documento de traslado': 'numero_traslado',
        u'n\xfamero de documento de traslado': 'numero_traslado',
        'numero doc traslado': 'numero_traslado',
        'numero doc. traslado': 'numero_traslado',
        'numero de docuemnto de traslado': 'numero_traslado',
        'numero docuemnto de traslado': 'numero_traslado',
        'number transfer document': 'numero_traslado',
        # --- Fecha de inicio del traslado (l10n_pe_edi_stock) ---
        'fecha de inicio del traslado': 'fecha_inicio_traslado',
        'fecha inicio del traslado': 'fecha_inicio_traslado',
        'fecha inicio traslado': 'fecha_inicio_traslado',
        'inicio del traslado': 'fecha_inicio_traslado',
        'departure start date': 'fecha_inicio_traslado',
    }

    # -------------------------------------------------------------------------
    # UTILIDADES
    # -------------------------------------------------------------------------
    def _leer_celda(self, hoja, fila, col_index):
        """Lee una celda de forma segura. Retorna None si la columna no existe."""
        if col_index is None or col_index < 0:
            return None
        try:
            valor = hoja.cell(fila, col_index).value
            return valor if valor != '' else None
        except (IndexError, Exception):
            return None

    def _normalizar_encabezado(self, texto):
        """Normaliza un encabezado: minúsculas, sin espacios extra."""
        if not texto:
            return ''
        return str(texto).strip().lower()

    def _detectar_columnas(self, hoja):
        """
        Lee fila 1 y mapea cada encabezado a su clave interna.
        Retorna dict {clave_interna: indice_columna}.
        """
        columnas = {}
        for col in range(hoja.ncols):
            valor_celda = hoja.cell(0, col).value
            if not valor_celda:
                continue

            encabezado = self._normalizar_encabezado(valor_celda)

            if encabezado in self.MAPEO_ENCABEZADOS:
                clave = self.MAPEO_ENCABEZADOS[encabezado]
                if clave not in columnas:
                    columnas[clave] = col
                    _logger.info(
                        "Columna '%s' (col %d) → %s", valor_celda, col, clave
                    )
            else:
                _logger.warning(
                    "Encabezado no reconocido: '%s' (col %d)", valor_celda, col
                )

        return columnas

    def _listar_encabezados(self, hoja):
        """Retorna cadena con los encabezados de fila 1."""
        headers = []
        for col in range(hoja.ncols):
            val = hoja.cell(0, col).value
            if val:
                headers.append("'%s'" % val)
        return ', '.join(headers) if headers else '(vacío)'

    # -------------------------------------------------------------------------
    # MÉTODO PRINCIPAL DE IMPORTACIÓN
    # -------------------------------------------------------------------------
    def importar_transferencias_desde_excel(self):
        """
        Lee el archivo Excel y crea las transferencias de inventario.

        FUNCIONAMIENTO FLEXIBLE:
        ─────────────────────────
        • Detecta columnas automáticamente por nombre de encabezado.
        • Solo OBLIGATORIAS: "Producto" y "Demanda Inicial" (o sinónimos).
        • Todo lo demás es OPCIONAL:
          - Sin "ID del Picking" → agrupa por Propietario (un picking por propietario).
          - Sin "Propietario" ni "ID del Picking" → crea UN picking para todo.
          - Sin "Descripción" → se llena automáticamente con el nombre del producto.
          - Sin "Contacto" → partner_id queda vacío.
          - Sin "Seguimiento/Lote/Serie" → sin trazabilidad.
        • Búsqueda de partners: prioridad RUC (columna "RUC de ...") sobre
          nombre. Si hay RUC en la fila, se busca por vat exacto; si no,
          cae al nombre (compat con plantillas antiguas).
        • Soporta encabezados en español e inglés, con o sin tildes.
        • Soporta lotes: 1 por fila, varios por fila (coma), o filas de continuación.
        """
        if not self.archivo:
            raise ValidationError(_("Por favor seleccione un archivo Excel."))

        # --- Abrir archivo ---
        try:
            file_content = base64.decodebytes(self.archivo)
            workbook = xlrd.open_workbook(file_contents=file_content)
        except Exception as e:
            raise ValidationError(
                _("No se pudo leer el archivo.\n\n"
                  "Asegúrese de que sea formato .xls (Excel 97-2003).\n"
                  "Si es .xlsx, guárdelo como .xls primero.\n\n"
                  "Error: %s") % str(e)
            )

        hoja = workbook.sheet_by_index(0)
        total_filas = hoja.nrows

        if total_filas <= 1:
            raise ValidationError(
                _("El archivo está vacío o solo tiene encabezados.")
            )

        # =============================================================
        # PASO 1: DETECTAR COLUMNAS
        # =============================================================
        columnas = self._detectar_columnas(hoja)

        if 'producto' not in columnas:
            raise ValidationError(
                _("No se encontró la columna PRODUCTO.\n\n"
                  "Ponga un encabezado 'Producto' o 'Product' en la fila 1.\n\n"
                  "Encabezados encontrados: %s") % self._listar_encabezados(hoja)
            )
        if 'cantidad' not in columnas:
            raise ValidationError(
                _("No se encontró la columna CANTIDAD / DEMANDA INICIAL.\n\n"
                  "Ponga un encabezado 'Demanda Inicial', 'Cantidad' o 'Qty'.\n\n"
                  "Encabezados encontrados: %s") % self._listar_encabezados(hoja)
            )

        # Índices (None si no existe la columna)
        col = {
            'picking_id': columnas.get('picking_id'),
            'contacto': columnas.get('contacto'),
            'ruc_contacto': columnas.get('ruc_contacto'),
            'origen': columnas.get('origen'),
            'propietario': columnas.get('propietario'),
            'ruc_propietario': columnas.get('ruc_propietario'),
            'politica': columnas.get('politica_envio'),
            'producto': columnas.get('producto'),
            'descripcion': columnas.get('descripcion'),
            'cantidad': columnas.get('cantidad'),
            'seguimiento': columnas.get('seguimiento'),
            'lote': columnas.get('lote'),
            'serie': columnas.get('serie'),
            # Campos de transporte / traslado
            'ticket_pesaje': columnas.get('ticket_pesaje'),
            'fecha_ticket': columnas.get('fecha_ticket'),  # informativa, se ignora
            'transportista': columnas.get('transportista'),
            'ruc_transportista': columnas.get('ruc_transportista'),
            'guias_grr': columnas.get('guias_grr'),
            'guias_gtr': columnas.get('guias_gtr'),
            'placa': columnas.get('placa'),
            'tipo_transporte': columnas.get('tipo_transporte'),
            'tipo_doc_traslado': columnas.get('tipo_doc_traslado'),
            'serie_traslado': columnas.get('serie_traslado'),
            'numero_traslado': columnas.get('numero_traslado'),
            'fecha_inicio_traslado': columnas.get('fecha_inicio_traslado'),
        }

        # --- Variables de control ---
        pickings_creados = []
        diccionario_pickings = {}   # clave → stock.picking record
        picking_actual = None
        moves_con_lote = []         # [[stock.move, producto, [lotes], tipo, cantidad]]
        ultimo_move_lote_idx = None # Índice en moves_con_lote del último move con lotes
        pending_sql = {}            # {picking_id: {col: val}} — campos que se escriben después del confirm

        # =============================================================
        # PASO 2: RECORRER FILAS
        # =============================================================
        for fila in range(1, total_filas):

            # --- Leer celdas seguras ---
            id_picking       = self._leer_celda(hoja, fila, col['picking_id'])
            nombre_contacto  = self._leer_celda(hoja, fila, col['contacto'])
            ruc_contacto_val = self._leer_celda(hoja, fila, col['ruc_contacto'])
            documento_origen = self._leer_celda(hoja, fila, col['origen'])
            nombre_propietario  = self._leer_celda(hoja, fila, col['propietario'])
            ruc_propietario_val = self._leer_celda(hoja, fila, col['ruc_propietario'])
            politica_envio   = self._leer_celda(hoja, fila, col['politica'])
            valor_producto   = self._leer_celda(hoja, fila, col['producto'])
            descripcion      = self._leer_celda(hoja, fila, col['descripcion'])
            cantidad         = self._leer_celda(hoja, fila, col['cantidad'])
            seguimiento      = self._leer_celda(hoja, fila, col['seguimiento'])
            nombre_lote      = self._leer_celda(hoja, fila, col['lote'])
            numeros_serie    = self._leer_celda(hoja, fila, col['serie'])
            # Campos de transporte / traslado (picking-level)
            ticket_pesaje_val   = self._leer_celda(hoja, fila, col['ticket_pesaje'])
            transportista_val     = self._leer_celda(hoja, fila, col['transportista'])
            ruc_transportista_val = self._leer_celda(hoja, fila, col['ruc_transportista'])
            guias_grr_val       = self._leer_celda(hoja, fila, col['guias_grr'])
            guias_gtr_val       = self._leer_celda(hoja, fila, col['guias_gtr'])
            placa_val           = self._leer_celda(hoja, fila, col['placa'])
            tipo_transporte_val = self._leer_celda(hoja, fila, col['tipo_transporte'])
            tipo_doc_traslado_val = self._leer_celda(hoja, fila, col['tipo_doc_traslado'])
            serie_traslado_val  = self._leer_celda(hoja, fila, col['serie_traslado'])
            numero_traslado_val = self._leer_celda(hoja, fila, col['numero_traslado'])
            fecha_inicio_traslado_val = self._leer_celda(hoja, fila, col['fecha_inicio_traslado'])

            # ─────────────────────────────────────────────
            # CASO ESPECIAL: Fila de continuación de lote
            # Si NO hay producto NI cantidad, PERO SÍ hay lote
            # → es un lote adicional del último producto
            # Ejemplo:
            #   Fila 2: Producto=JE00005929, Qty=50, Lote=sierr
            #   Fila 3: (vacío), (vacío), Lote=carmen  ← continuación
            #   Fila 4: (vacío), (vacío), Lote=gisela  ← continuación
            # ─────────────────────────────────────────────
            lote_valor = nombre_lote or numeros_serie
            if not valor_producto and not cantidad and lote_valor:
                if ultimo_move_lote_idx is not None:
                    lote_str = str(lote_valor).strip()
                    moves_con_lote[ultimo_move_lote_idx][2].append(lote_str)
                else:
                    raise ValidationError(
                        _('Fila %s tiene un lote ("%s") pero no hay un '
                          'producto previo al cual asignarlo.')
                        % (fila + 1, lote_valor)
                    )
                continue

            # Saltar filas completamente vacías
            if not valor_producto and not cantidad:
                continue

            # ─────────────────────────────────────────────
            # CREAR O REUSAR PICKING
            # Prioridad de agrupación:
            #   1. Columna "Ticket de Pesaje" → agrupa por ticket
            #      (error duro si la columna existe pero la fila
            #       no trae ticket)
            #   2. Columna "ID del Picking" → agrupa por ID
            #   3. Propietario (fallback histórico)
            # ─────────────────────────────────────────────
            necesita_nuevo = False
            clave_agrupacion = None
            # Para agrupar por propietario preferimos el RUC si existe,
            # así no se separan pickings por typos en el nombre.
            if ruc_propietario_val:
                clave_propietario = 'RUC::%s' % self._normalizar_numero_excel(ruc_propietario_val)
            elif nombre_propietario:
                clave_propietario = str(nombre_propietario).strip().upper()
            else:
                clave_propietario = '__SIN_PROPIETARIO__'

            if col['ticket_pesaje'] is not None:
                # Columna Ticket presente → agrupa por ticket
                if not ticket_pesaje_val:
                    raise ValidationError(
                        _('La columna "Ticket de Pesaje" está presente '
                          'pero la fila %s no tiene valor. Cuando se '
                          'importa por ticket, todas las filas deben '
                          'tener uno.') % (fila + 1,)
                    )
                clave_agrupacion = 'TICKET::%s' % self._normalizar_numero_excel(ticket_pesaje_val)
                if clave_agrupacion in diccionario_pickings:
                    picking_actual = diccionario_pickings[clave_agrupacion]
                else:
                    necesita_nuevo = True
            elif col['picking_id'] is not None:
                # Hay columna ID Picking → agrupar por ID
                if id_picking:
                    if id_picking not in diccionario_pickings:
                        necesita_nuevo = True
                    else:
                        picking_actual = diccionario_pickings[id_picking]
                else:
                    if picking_actual is None:
                        necesita_nuevo = True
            else:
                # No hay columna ID Picking → agrupar por propietario
                if clave_propietario in diccionario_pickings:
                    picking_actual = diccionario_pickings[clave_propietario]
                else:
                    necesita_nuevo = True

            if necesita_nuevo:
                campos_transporte = {
                    'ticket_pesaje': ticket_pesaje_val,
                    'transportista': transportista_val,
                    'ruc_transportista': ruc_transportista_val,
                    'guias_grr': guias_grr_val,
                    'guias_gtr': guias_gtr_val,
                    'placa': placa_val,
                    'tipo_transporte': tipo_transporte_val,
                    'tipo_doc_traslado': tipo_doc_traslado_val,
                    'serie_traslado': serie_traslado_val,
                    'numero_traslado': numero_traslado_val,
                    'fecha_inicio_traslado': fecha_inicio_traslado_val,
                }
                picking_actual = self._crear_picking(
                    nombre_contacto, documento_origen,
                    nombre_propietario, politica_envio, fila,
                    campos_transporte=campos_transporte,
                    pending_sql=pending_sql,
                    ruc_contacto=ruc_contacto_val,
                    ruc_propietario=ruc_propietario_val,
                )
                pickings_creados.append(picking_actual.id)
                if clave_agrupacion is not None:
                    diccionario_pickings[clave_agrupacion] = picking_actual
                elif col['picking_id'] is not None and id_picking:
                    diccionario_pickings[id_picking] = picking_actual
                else:
                    diccionario_pickings[clave_propietario] = picking_actual

            # ─────────────────────────────────────────────
            # BUSCAR PRODUCTO
            # ─────────────────────────────────────────────
            if not valor_producto:
                raise ValidationError(
                    _('Producto vacío en fila %s.') % (fila + 1,)
                )

            producto_record = self._buscar_producto(valor_producto, fila)

            # ─────────────────────────────────────────────
            # VALIDAR CANTIDAD
            # ─────────────────────────────────────────────
            if not cantidad:
                raise ValidationError(
                    _('Cantidad vacía en fila %s.') % (fila + 1,)
                )
            try:
                cantidad_float = float(cantidad)
            except (ValueError, TypeError):
                raise ValidationError(
                    _('Cantidad "%s" no es número válido. Fila: %s.')
                    % (cantidad, fila + 1)
                )
            if cantidad_float <= 0:
                raise ValidationError(
                    _('La cantidad debe ser mayor a 0. Fila: %s.') % (fila + 1,)
                )

            # ─────────────────────────────────────────────
            # CREAR stock.move (SIN lotes por ahora)
            # description_picking único para evitar que Odoo
            # fusione moves del mismo producto al confirmar
            # ─────────────────────────────────────────────
            nombre_desc = descripcion if descripcion else producto_record.display_name

            vals_move = {
                'product_id': producto_record.id,
                'product_uom_qty': cantidad_float,
                'picking_id': picking_actual.id,
                'name': nombre_desc,
                'description_picking': '%s (Fila %s)' % (nombre_desc, fila + 1),
                'location_id': self.ubicacion_origen_id.id,
                'location_dest_id': self.ubicacion_destino_id.id,
            }

            mov_temp = self.env['stock.move'].new(vals_move)
            mov_temp._onchange_product_id()
            vals_final = mov_temp._convert_to_write({
                name: mov_temp[name] for name in mov_temp._cache
            })
            vals_final['name'] = nombre_desc
            vals_final['description_picking'] = '%s (Fila %s)' % (nombre_desc, fila + 1)
            movimiento = self.env['stock.move'].create(vals_final)

            # ─────────────────────────────────────────────
            # GUARDAR INFO DE LOTES para crear move.lines
            # Soporta: lotes separados por coma Y filas de
            # continuación (se agregan después en el loop)
            # ─────────────────────────────────────────────
            seg_str = str(seguimiento).strip().lower() if seguimiento else ''
            ultimo_move_lote_idx = None  # Reset

            if seg_str in ('lot', 'serial'):
                lote_inicial = nombre_lote or numeros_serie
                lotes_lista = []

                if lote_inicial:
                    # Soportar comas en la misma celda también
                    for l in str(lote_inicial).split(','):
                        l = l.strip()
                        if l:
                            lotes_lista.append(l)

                # Guardar: [movimiento, producto, [lotes], tipo, cantidad]
                moves_con_lote.append([
                    movimiento, producto_record, lotes_lista,
                    seg_str, cantidad_float
                ])
                ultimo_move_lote_idx = len(moves_con_lote) - 1

        # =============================================================
        # PASO 3: CONFIRMAR + CREAR MOVE.LINES CON LOTES
        # =============================================================
        if not pickings_creados:
            raise ValidationError(
                _("No se creó ninguna transferencia. Verifique los datos.")
            )

        # Confirmar y asignar SIEMPRE
        for pid in pickings_creados:
            p = self.env['stock.picking'].browse(pid)
            p.action_confirm()
            p.action_assign()

        # SQL post-confirm: escribir campos de invoice_type_document_extension DESPUÉS
        # de que todos los computes de action_confirm() hayan corrido, para que no los pisen.
        self._ejecutar_sql_pendiente(pending_sql)

        # Escribir lotes/seriales + quantity en las move.lines generadas
        for movimiento, producto, lotes_nombres, tipo, cantidad in moves_con_lote:
            if not lotes_nombres:
                continue

            # Crear/buscar cada lote y armar la data
            lotes_data = []
            if tipo == 'lot':
                cant_por_lote = cantidad / len(lotes_nombres)
                for nombre in lotes_nombres:
                    lote_rec = self._obtener_o_crear_lote(nombre, producto)
                    lotes_data.append((lote_rec, cant_por_lote))
            elif tipo == 'serial':
                for nombre in lotes_nombres:
                    sn_rec = self._obtener_o_crear_lote(nombre, producto)
                    lotes_data.append((sn_rec, 1))

            self._aplicar_lotes_en_move_lines(movimiento, lotes_data)

        # Si el usuario quiere Validado → ejecutar la transferencia completa
        # Odoo 18: el campo `stock.move.line.qty_done` fue eliminado en v18.
        # En su lugar se usa `quantity` (Float, con inverse `_set_quantity`).
        if self.estado == 'done':
            for pid in pickings_creados:
                p = self.env['stock.picking'].browse(pid)
                for ml in p.move_line_ids:
                    if not ml.quantity and ml.product_uom_qty:
                        ml.quantity = ml.product_uom_qty
                p.button_validate()

        action = self.env.ref('stock.action_picking_tree_all').sudo().read()[0]
        action['domain'] = [('id', 'in', pickings_creados)]
        return action

    # -------------------------------------------------------------------------
    # BÚSQUEDA DE PARTNERS POR RUC
    # -------------------------------------------------------------------------
    def _buscar_partner_por_ruc(self, ruc, fila, contexto='Contacto'):
        """
        Busca un res.partner por RUC exacto.

        Estrategia: busca en `vat` (campo estándar de Odoo donde vive el RUC
        aun con l10n_pe instalado) y, si existen en el modelo, también en
        `l10n_pe_latam_identification_number` y `l10n_latam_identification_number`
        (fallback para instalaciones custom).

        Normaliza floats de xlrd (20512081372.0 → '20512081372').
        Devuelve el id del partner o lanza ValidationError si no lo encuentra.
        """
        if not ruc:
            return False

        ruc_norm = self._normalizar_numero_excel(ruc)
        partner_fields = self.env['res.partner']._fields

        # Campos candidatos donde puede vivir el número de RUC
        campos_ruc = ['vat']
        for extra in ('l10n_pe_latam_identification_number',
                      'l10n_latam_identification_number'):
            if extra in partner_fields:
                campos_ruc.append(extra)

        # Armar dominio OR sobre todos los campos candidatos
        # ['|', '|', (a,=,x), (b,=,x), (c,=,x)]
        domain = ['|'] * (len(campos_ruc) - 1)
        for f in campos_ruc:
            domain.append((f, '=', ruc_norm))

        rec = self.env['res.partner'].search(domain, limit=1)
        if not rec:
            raise ValidationError(
                _('%s con RUC "%s" no encontrado en el sistema. '
                  'Verifique que el partner exista y tenga el RUC registrado. '
                  'Fila: %s') % (contexto, ruc_norm, fila + 1)
            )
        return rec.id

    # -------------------------------------------------------------------------
    # MÉTODOS DE CREACIÓN
    # -------------------------------------------------------------------------
    def _crear_picking(self, nombre_contacto, documento_origen,
                       nombre_propietario, politica_envio, fila,
                       campos_transporte=None, pending_sql=None,
                       ruc_contacto=None, ruc_propietario=None):
        """Crea un stock.picking. Todos los campos son opcionales salvo los base.

        Búsqueda de partners: prioridad RUC sobre nombre.
        - Si viene RUC → busca por vat exacto (helper _buscar_partner_por_ruc).
        - Si no viene RUC pero sí nombre → cae al comportamiento anterior
          (search por name exacto y luego ilike, como fallback compat).
        """
        Contacto = self.env['res.partner']
        campos_transporte = campos_transporte or {}
        picking_fields = self.env['stock.picking']._fields

        # ── Contacto (opcional) — prioridad: RUC > nombre ──
        contacto_id = False
        if ruc_contacto:
            contacto_id = self._buscar_partner_por_ruc(
                ruc_contacto, fila, contexto='Contacto'
            )
        elif nombre_contacto:
            c = str(nombre_contacto).strip()
            rec = Contacto.search([('name', '=', c)], limit=1)
            if not rec:
                rec = Contacto.search([('name', 'ilike', c)], limit=1)
            if not rec:
                raise ValidationError(
                    _('Contacto "%s" no encontrado. Fila: %s') % (c, fila + 1)
                )
            contacto_id = rec.id

        # ── Propietario (opcional) — prioridad: RUC > nombre ──
        propietario_id = False
        if ruc_propietario:
            propietario_id = self._buscar_partner_por_ruc(
                ruc_propietario, fila, contexto='Propietario'
            )
        elif nombre_propietario:
            p = str(nombre_propietario).strip()
            rec = Contacto.search([('name', '=', p)], limit=1)
            if not rec:
                rec = Contacto.search([('name', 'ilike', p)], limit=1)
            if not rec:
                raise ValidationError(
                    _('Propietario "%s" no encontrado. Fila: %s') % (p, fila + 1)
                )
            propietario_id = rec.id

        # Política de envío
        move_type = 'direct'
        if politica_envio:
            pl = str(politica_envio).strip().lower()
            if 'all' in pl or 'todos' in pl:
                move_type = 'one'

        vals = {
            'company_id': self.company_id.id,
            'picking_type_id': self.tipo_operacion_id.id,
            'location_id': self.ubicacion_origen_id.id,
            'location_dest_id': self.ubicacion_destino_id.id,
            'move_type': move_type,
        }
        if contacto_id:
            vals['partner_id'] = contacto_id
        if documento_origen:
            vals['origin'] = str(documento_origen).strip()
        if propietario_id:
            vals['owner_id'] = propietario_id

        # ── Transportista (jeal_stock_picking_transport) — prioridad: RUC > nombre ──
        ruc_transportista = campos_transporte.get('ruc_transportista')
        nombre_transportista = campos_transporte.get('transportista')
        if 'transportista_id' in picking_fields:
            if ruc_transportista:
                vals['transportista_id'] = self._buscar_partner_por_ruc(
                    ruc_transportista, fila, contexto='Transportista'
                )
            elif nombre_transportista:
                t = str(nombre_transportista).strip()
                rec = Contacto.search([('name', '=', t)], limit=1)
                if not rec:
                    rec = Contacto.search([('name', 'ilike', t)], limit=1)
                if not rec:
                    raise ValidationError(
                        _('Transportista "%s" no encontrado. Fila: %s')
                        % (t, fila + 1)
                    )
                vals['transportista_id'] = rec.id

        # ── Guías GRR (jeal_stock_picking_transport) ──
        guias_grr = campos_transporte.get('guias_grr')
        if guias_grr and 'guias_grr' in picking_fields:
            vals['guias_grr'] = str(guias_grr).strip()

        # ── Guías GRT (jeal_stock_picking_transport) ──
        guias_gtr = campos_transporte.get('guias_gtr')
        if guias_gtr and 'guias_gtr' in picking_fields:
            vals['guias_gtr'] = str(guias_gtr).strip()

        # ── Placa (jeal_stock_picking_transport) ──
        placa = campos_transporte.get('placa')
        if placa and 'placa' in picking_fields:
            vals['placa'] = str(placa).strip()

        # ── Ticket de pesaje (jeal_stock_picking_transport) ──
        ticket_pesaje = campos_transporte.get('ticket_pesaje')
        if ticket_pesaje and 'ticket_pesaje' in picking_fields:
            try:
                vals['ticket_pesaje'] = self._normalizar_numero_excel(ticket_pesaje)
            except (ValueError, TypeError):
                _logger.warning(
                    "Ticket de pesaje '%s' no es valor válido (fila %s), se omite.",
                    ticket_pesaje, fila + 1,
                )

        # ── Tipo de transporte (l10n_pe_edi_stock) ──
        tipo_transporte = campos_transporte.get('tipo_transporte')
        if tipo_transporte and 'l10n_pe_edi_transport_type' in picking_fields:
            tipo_code = self._map_tipo_transporte(tipo_transporte)
            if tipo_code:
                vals['l10n_pe_edi_transport_type'] = tipo_code

        # ── Fecha de inicio del traslado (l10n_pe_edi_stock) ──
        fecha_inicio = campos_transporte.get('fecha_inicio_traslado')
        if fecha_inicio and 'l10n_pe_edi_departure_start_date' in picking_fields:
            fecha_str = self._parsear_fecha_excel(fecha_inicio)
            if fecha_str:
                vals['l10n_pe_edi_departure_start_date'] = fecha_str

        # ── Tipo documento de traslado (invoice_type_document_extension) ──
        tipo_doc_traslado = campos_transporte.get('tipo_doc_traslado')
        if tipo_doc_traslado and 'transfer_document_type_id' in picking_fields:
            doc_id = self._buscar_tipo_doc_traslado(tipo_doc_traslado)
            if doc_id:
                vals['transfer_document_type_id'] = doc_id

        # Sacar tipo_doc_traslado de vals antes de create
        # (el compute de invoice_type_document_extension lo sobreescribe en create)
        tipo_doc_id_para_sql = vals.pop('transfer_document_type_id', None)

        picking = self.env['stock.picking'].create(vals)

        # ── Campos de invoice_type_document_extension: SQL directo ──
        # _compute_transfer_data_picking sobreescribe estos campos con None
        # después del create, así que usamos SQL para saltarnos el compute.
        sql_cols = []
        sql_vals = []
        if tipo_doc_id_para_sql and 'transfer_document_type_id' in picking_fields:
            sql_cols.append('transfer_document_type_id')
            sql_vals.append(tipo_doc_id_para_sql)
        serie_traslado = campos_transporte.get('serie_traslado')
        if serie_traslado and 'serie_transfer_document' in picking_fields:
            sql_cols.append('serie_transfer_document')
            sql_vals.append(self._normalizar_numero_excel(serie_traslado))
        numero_traslado = campos_transporte.get('numero_traslado')
        if numero_traslado and 'number_transfer_document' in picking_fields:
            sql_cols.append('number_transfer_document')
            sql_vals.append(self._normalizar_numero_excel(numero_traslado))

        # Guardar para ejecutar DESPUÉS de action_confirm() — el compute
        # _compute_transfer_data_picking pisa estos campos durante el flush
        # que ocurre en action_confirm(), así que escribimos post-confirm.
        if sql_cols and pending_sql is not None:
            pending_sql[picking.id] = dict(zip(sql_cols, sql_vals))

        return picking

    def _ejecutar_sql_pendiente(self, pending_sql):
        """Escribe los campos de invoice_type_document_extension directamente en DB.
        Se llama DESPUÉS de action_confirm/action_assign para que los computes
        almacenados no pisen los valores que importamos."""
        if not pending_sql:
            return
        picking_fields = self.env['stock.picking']._fields
        for picking_id, sql_data in pending_sql.items():
            if not sql_data:
                continue
            cols = list(sql_data.keys())
            vals = list(sql_data.values())
            set_clause = ', '.join('"%s" = %%s' % c for c in cols)
            query = 'UPDATE stock_picking SET %s WHERE id = %%s' % set_clause
            self.env.cr.execute(query, vals + [picking_id])
            picking = self.env['stock.picking'].browse(picking_id)
            picking.invalidate_recordset([c for c in cols if c in picking_fields])

    def _buscar_producto(self, valor_producto, fila):
        """Busca producto por nombre, código o barcode según configuración."""
        Producto = self.env['product.product']
        val = str(valor_producto).strip()

        # xlrd puede leer códigos numéricos como float (50.0 → "50")
        val_int = val
        try:
            if float(val) == int(float(val)):
                val_int = str(int(float(val)))
        except (ValueError, TypeError):
            pass

        rec = False
        company_domain = ('company_id', 'in', [self.company_id.id, False])

        if self.importar_producto_por == 'name':
            rec = Producto.search(
                [('name', '=', val), company_domain], limit=1
            )
            if not rec:
                rec = Producto.search([('name', 'ilike', val)], limit=1)

        elif self.importar_producto_por == 'code':
            for v in [val, val_int]:
                rec = Producto.search(
                    [('default_code', '=', v), company_domain], limit=1
                )
                if not rec:
                    rec = Producto.search(
                        [('default_code', '=', v)], limit=1
                    )
                if rec:
                    break

        elif self.importar_producto_por == 'barcode':
            for v in [val, val_int]:
                rec = Producto.search(
                    [('barcode', '=', v), company_domain], limit=1
                )
                if not rec:
                    rec = Producto.search(
                        [('barcode', '=', v)], limit=1
                    )
                if rec:
                    break

        if not rec:
            metodo = dict(
                self._fields['importar_producto_por'].selection
            ).get(self.importar_producto_por, '')
            raise ValidationError(
                _('Producto "%s" no encontrado.\n'
                  'Fila: %s | Método: %s\n\n'
                  'Verifique que el producto exista en Odoo y que el valor '
                  'coincida exactamente.') % (val, fila + 1, metodo)
            )
        return rec

    # -------------------------------------------------------------------------
    # HELPERS NUEVOS CAMPOS
    # -------------------------------------------------------------------------
    def _parsear_fecha_excel(self, valor):
        """Convierte un valor de celda Excel a 'YYYY-MM-DD' para campos date de Odoo.
        xlrd devuelve fechas formateadas como float (serial Excel) o como string."""
        import datetime
        if valor is None:
            return False
        if isinstance(valor, float):
            try:
                dt = xlrd.xldate_as_datetime(valor, 0)
                return dt.strftime('%Y-%m-%d')
            except Exception:
                pass
        val_str = str(valor).strip()
        if not val_str:
            return False
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d.%m.%Y'):
            try:
                return datetime.datetime.strptime(val_str, fmt).strftime('%Y-%m-%d')
            except ValueError:
                pass
        _logger.warning("No se pudo parsear la fecha '%s'. Use formato DD/MM/YYYY.", valor)
        return False

    def _normalizar_numero_excel(self, valor):
        """
        xlrd lee celdas numéricas como float (ej: 2.0, 9.0, 3534.0).
        Retorna la representación entera como string cuando corresponde.
        """
        try:
            f = float(str(valor).strip())
            if f == int(f):
                return str(int(f))
        except (ValueError, TypeError):
            pass
        return str(valor).strip()

    def _map_tipo_transporte(self, valor):
        """Mapea texto del Excel al código de selección de l10n_pe_edi_transport_type.
        Acepta: 1, 01, 1.0, Público / 2, 02, 2.0, Privado."""
        v = self._normalizar_numero_excel(valor).lower()
        publico = ('1', '01', 'publico', 'público', 'public',
                   'transporte publico', 'transporte público')
        privado = ('2', '02', 'privado', 'private', 'transporte privado')
        if v in publico:
            return '01'
        if v in privado:
            return '02'
        _logger.warning(
            "Tipo de transporte '%s' no reconocido. "
            "Use: 1/01/Público o 2/02/Privado.", valor
        )
        return False

    def _buscar_tipo_doc_traslado(self, valor):
        """Busca l10n_latam.document.type por código o nombre.
        Normaliza valores numéricos de xlrd (9.0 → busca '9' y '09')."""
        if 'l10n_latam.document.type' not in self.env.registry:
            return False
        v_raw = self._normalizar_numero_excel(valor)          # '9.0' → '9'
        v_pad = v_raw.zfill(2)                                # '9'  → '09'
        rec = self.env['l10n_latam.document.type'].search(
            [('code', 'in', [v_raw, v_pad])], limit=1
        )
        if not rec:
            rec = self.env['l10n_latam.document.type'].search(
                [('name', 'ilike', v_raw)], limit=1
            )
        if not rec:
            _logger.warning(
                "Tipo de documento de traslado '%s' no encontrado "
                "en l10n_latam.document.type.", valor
            )
        return rec.id if rec else False

    # -------------------------------------------------------------------------
    # TRAZABILIDAD
    # -------------------------------------------------------------------------
    def _obtener_o_crear_lote(self, nombre, producto):
        """Busca un lote/serial. Si no existe, lo crea automáticamente."""
        lote_rec = self.env['stock.lot'].search([
            ('name', '=', nombre),
            ('product_id', '=', producto.id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        if not lote_rec:
            lote_rec = self.env['stock.lot'].create({
                'name': nombre,
                'product_id': producto.id,
                'company_id': self.company_id.id,
            })
        return lote_rec

    def _aplicar_lotes_en_move_lines(self, movimiento, lotes_data):
        """
        Escribe los lotes/seriales en las move.line del movimiento.

        Estrategia robusta para recepciones en Odoo 18:
        1. Forzar tracking='lot' en el producto (si no, Odoo ignora lot_id)
        2. Usar lot_name además de lot_id
        3. Escribir en move.lines existentes en vez de borrar y recrear cuando
           el borrado no está permitido.
        """
        if not lotes_data:
            return

        # Verificar que el move aún existe (Odoo pudo fusionarlo)
        if not movimiento.exists():
            _logger.warning(
                "stock.move %s ya no existe (fue fusionado por Odoo). "
                "Los lotes se omitirán.", movimiento.id
            )
            return

        # ── PASO CLAVE: Forzar tracking='lot' en el producto ──
        # Si el producto no tiene tracking='lot', Odoo IGNORA el lot_id
        producto = movimiento.product_id
        if producto.tracking == 'none':
            producto.tracking = 'lot'

        picking = movimiento.picking_id

        # ── Intentar limpiar move.lines existentes (vacías) ──
        existing = movimiento.move_line_ids
        try:
            if existing:
                existing.unlink()
        except Exception:
            _logger.warning(
                "No se pudieron eliminar move.lines existentes del move %s, "
                "se intentará escribir sobre ellas.", movimiento.id
            )
            # Si no se pueden borrar, escribir en la primera.
            # Odoo 18: `qty_done` → `quantity` en stock.move.line.
            if existing and len(lotes_data) == 1:
                lote_rec, qty = lotes_data[0]
                existing[0].write({
                    'lot_id': lote_rec.id,
                    'lot_name': lote_rec.name,
                    'quantity': qty,
                })
                return

        # ── Crear move.lines nuevas con lote ──
        # Odoo 18: el campo de cantidad realmente movida en la move.line
        # cambió de `qty_done` (v16) a `quantity` (v17+).
        for lote_rec, qty in lotes_data:
            vals = {
                'move_id': movimiento.id,
                'picking_id': picking.id,
                'product_id': producto.id,
                'lot_id': lote_rec.id,
                'lot_name': lote_rec.name,
                'quantity': qty,
                'product_uom_id': movimiento.product_uom.id,
                'location_id': movimiento.location_id.id,
                'location_dest_id': movimiento.location_dest_id.id,
            }
            self.env['stock.move.line'].create(vals)