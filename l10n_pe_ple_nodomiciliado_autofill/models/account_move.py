# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Tipos de comprobante que SUNAT acepta en el campo 10 del RCE No Domiciliados
# (tipo de comprobante que sustenta el credito fiscal).
NODOM_SUSTENTO_ALLOWED_CODES = ('00', '46', '50', '51', '52', '53')
# Codigos que se pueden elegir en el sustento. Incluye el 91 porque el
# autorrelleno lo carga por defecto (editable por el usuario).
NODOM_SUSTENTO_SELECTABLE_CODES = NODOM_SUSTENTO_ALLOWED_CODES + ('91',)
# Sustentos que exigen el año de emision de la DUA/DSI.
NODOM_SUSTENTO_DUA_CODES = ('50', '52')
# Tipo de comprobante (cabecera) permitido en el registro de No Domiciliados.
NODOM_HEADER_ALLOWED_CODES = ('00', '91', '97', '98')


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Pestana No Domiciliado (sustento, campos 10 a 13 del TXT).
    # Autorrelleno al marcar No Domiciliado: Tipo documento = 91 y Serie /
    # Correlativo desde la Referencia de factura. Todos siguen editables.
    # copy=False: al duplicar se vuelven a calcular para la nueva factura.
    inv_type_document = fields.Many2one(
        compute='_compute_inv_type_document_nodom',
        store=True,
        readonly=False,
        domain=[
            ('code', 'in', NODOM_SUSTENTO_SELECTABLE_CODES),
            ('country_id.code', '=', 'PE'),
        ],
        copy=False,
    )
    inv_serie = fields.Char(
        compute='_compute_inv_serie_correlative_nodom',
        store=True,
        readonly=False,
        copy=False,
    )
    inv_year_dua_dsi = fields.Char(copy=False)
    inv_correlative = fields.Char(
        compute='_compute_inv_serie_correlative_nodom',
        store=True,
        readonly=False,
        copy=False,
    )
    inv_type_document_code = fields.Char(
        related='inv_type_document.code',
        string='Código del sustento',
    )

    # Tipo de renta: se hereda del proveedor al crear la factura. No pisa un
    # valor elegido por el usuario.
    type_rent_id = fields.Many2one(
        compute='_compute_type_rent_nodom',
        store=True,
        readonly=False,
    )

    # CDI: se autocompleta (la ayuda del campo lo indicaba, pero no habia
    # codigo que lo hiciera). No pisa un valor elegido por el usuario.
    cdi = fields.Selection(
        compute='_compute_cdi_nodom',
        store=True,
        readonly=False,
    )

    # Tipo de documento del propio comprobante (campo 4 del TXT): se mantiene
    # el 91 para No Domiciliado, pero respetando el calculo estandar de Odoo
    # para el resto de facturas.
    l10n_latam_document_type_id = fields.Many2one(
        compute='_compute_l10n_latam_document_type_id_nodom',
        store=True,
        readonly=False,
    )

    def _nodom_document_type_depends(self):
        base_method = getattr(type(self), '_compute_l10n_latam_document_type', None)
        depends = getattr(base_method, '_depends', ()) if base_method else ()
        if callable(depends):
            depends = depends(self)
        return tuple(depends) + ('is_nodomicilied',)

    @api.depends(lambda self: self._nodom_document_type_depends())
    def _compute_l10n_latam_document_type_id_nodom(self):
        # Primero el calculo estandar (l10n_latam_invoice_document y herencias).
        if hasattr(self, '_compute_l10n_latam_document_type'):
            self._compute_l10n_latam_document_type()
        nodom_moves = self.filtered('is_nodomicilied')
        if not nodom_moves:
            return
        doc_91 = self.env['l10n_latam.document.type'].search(
            [('code', '=', '91'), ('country_id.code', '=', 'PE')],
            limit=1,
        )
        if doc_91:
            nodom_moves.l10n_latam_document_type_id = doc_91

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        # invoice_validation_by_document asigna Boleta/Factura segun el tipo de
        # identificacion del socio y pisa el 91. Para No Domiciliado se vuelve
        # a asignar el 91 despues de esa logica.
        res = super()._onchange_partner_id()
        if self.is_nodomicilied and self.move_type in ('in_invoice', 'in_refund'):
            doc_91 = self.env['l10n_latam.document.type'].search(
                [('code', '=', '91'), ('country_id.code', '=', 'PE')],
                limit=1,
            )
            if doc_91:
                self.l10n_latam_document_type_id = doc_91
        return res

    # -------------------------------------------------------------------------
    # Autorrelleno de la pestana No Domiciliado (editable)
    # -------------------------------------------------------------------------

    @staticmethod
    def _split_ref_serie_correlative(ref):
        """'E001-123' -> ('E001', '123'); sin guion -> ('', ref)."""
        ref = (ref or '').strip()
        if not ref:
            return False, False
        if '-' in ref:
            serie, correlative = ref.split('-', 1)
            return serie.strip(), correlative.strip()
        return '', ref

    @api.depends('is_nodomicilied')
    def _compute_inv_type_document_nodom(self):
        doc_91 = self.env['l10n_latam.document.type'].search(
            [('code', '=', '91'), ('country_id.code', '=', 'PE')],
            limit=1,
        )
        for move in self:
            # Solo se llena si esta vacio: respeta lo que elija el usuario.
            if move.is_nodomicilied and not move.inv_type_document and doc_91:
                move.inv_type_document = doc_91

    @api.depends('is_nodomicilied', 'ref')
    def _compute_inv_serie_correlative_nodom(self):
        for move in self:
            if not move.is_nodomicilied or not move.ref:
                continue
            serie, correlative = move._split_ref_serie_correlative(move.ref)
            move.inv_serie = serie
            move.inv_correlative = correlative

    @api.constrains('is_nodomicilied', 'inv_type_document')
    def _check_nodom_inv_type_document(self):
        for move in self:
            if (
                move.is_nodomicilied
                and move.inv_type_document
                and move.inv_type_document.code not in NODOM_SUSTENTO_SELECTABLE_CODES
            ):
                raise ValidationError(_(
                    "Factura %(move)s: el tipo de documento de la pestaña No "
                    "Domiciliado debe ser uno de %(codes)s. "
                    "Valor actual: (%(code)s) %(name)s.",
                    move=move.display_name,
                    codes=', '.join(NODOM_SUSTENTO_SELECTABLE_CODES),
                    code=move.inv_type_document.code,
                    name=move.inv_type_document.name,
                ))

    # -------------------------------------------------------------------------
    # CDI (convenio para evitar la doble imposicion)
    # -------------------------------------------------------------------------

    def _get_nodom_cdi_code(self):
        """Codigo CDI segun el contacto o, en su defecto, el pais del proveedor.

        - Convenio cargado en el contacto (double_taxation), si existe.
        - Codigo de convenio del pais (l10n_pe_agreement_code).
        - Pais sin codigo de convenio: '00' (Ninguno).
        - Proveedor sin pais: False (lo exige la validacion al publicar).
        """
        self.ensure_one()
        valid_codes = dict(self._fields['cdi'].selection)
        partner = self.partner_id
        if not partner:
            return False
        if 'double_taxation' in partner._fields:
            convenio = partner.double_taxation or partner.commercial_partner_id.double_taxation
            if convenio:
                code = str(convenio).zfill(2)
                if code in valid_codes:
                    return code
        country = partner.country_id
        if not country:
            return False
        agreement = (
            country.l10n_pe_agreement_code
            if 'l10n_pe_agreement_code' in country._fields else False
        )
        if agreement:
            code = str(agreement).strip().zfill(2)
            return code if code in valid_codes else False
        return '00'

    # Solo depende de campos de la propia factura: cambiar el pais de un
    # contacto no recalcula facturas existentes.
    @api.depends('is_nodomicilied', 'partner_id')
    def _compute_cdi_nodom(self):
        for move in self:
            if not move.is_nodomicilied or move.cdi:
                continue
            code = move._get_nodom_cdi_code()
            if code:
                move.cdi = code

    @api.depends('is_nodomicilied', 'partner_id')
    def _compute_type_rent_nodom(self):
        for move in self:
            if not move.is_nodomicilied or move.type_rent_id:
                continue
            partner = move.partner_id
            type_rent = (
                partner.nodom_type_rent_id
                or partner.commercial_partner_id.nodom_type_rent_id
            )
            if type_rent:
                move.type_rent_id = type_rent

    # -------------------------------------------------------------------------
    # Campos obligatorios al publicar
    # -------------------------------------------------------------------------

    def _get_nodom_missing_fields(self):
        self.ensure_one()
        missing = []
        partner = self.partner_id
        header_code = self.l10n_latam_document_type_id.code
        if header_code not in NODOM_HEADER_ALLOWED_CODES:
            missing.append(_(
                'Tipo de documento de la cabecera (debe ser %s; actual: %s)',
                ', '.join(NODOM_HEADER_ALLOWED_CODES), header_code or '-',
            ))
        if not (self.ref or '').strip():
            missing.append(_('Número del comprobante (Referencia de factura)'))
        if self.inv_type_document.code in NODOM_SUSTENTO_DUA_CODES and not self.inv_year_dua_dsi:
            missing.append(_('Año de emisión DUA/DSI del sustento'))
        if not self.type_rent_id:
            missing.append(_('Tipo de Renta'))
        if not self.cdi:
            missing.append(_('CDI (convenio para evitar la doble imposición)'))
        if not (partner.name or '').strip():
            missing.append(_('Razón social del proveedor'))
        if not partner.country_id:
            missing.append(_('País del proveedor'))
        elif not partner.country_id.l10n_pe_sunat_code:
            missing.append(_('Código SUNAT (Tabla 35) del país %s', partner.country_id.name))
        if not partner.vat:
            missing.append(_('Número de identificación del proveedor'))
        return missing

    def _check_nodom_required_fields(self):
        errors = []
        moves = self.filtered(
            lambda m: m.is_nodomicilied and m.move_type in ('in_invoice', 'in_refund')
        )
        for move in moves:
            missing = move._get_nodom_missing_fields()
            if missing:
                errors.append('%s (%s): %s' % (
                    move.ref or move.display_name,
                    move.partner_id.display_name or '-',
                    ', '.join(missing),
                ))
        if errors:
            raise UserError(_(
                "No se puede publicar: faltan datos obligatorios para el "
                "registro de compras No Domiciliados.\n\n%s",
                '\n'.join('- ' + e for e in errors),
            ))

    def _post(self, soft=True):
        self._check_nodom_required_fields()
        return super()._post(soft=soft)