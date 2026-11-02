from odoo import api, fields, models


class AccountAsset(models.Model):
    _inherit = "account.asset"

    # Ubicación del activo (mismo esquema que la dirección de contactos en Perú:
    # provincia = res.city, distrito = l10n_pe.res.city.district filtrado por
    # la provincia).
    l10n_pe_asset_address = fields.Char(string="Dirección")
    l10n_pe_asset_province_id = fields.Many2one(
        comodel_name="res.city",
        string="Provincia",
        domain="[('country_id.code', '=', 'PE')]",
    )
    l10n_pe_asset_district_id = fields.Many2one(
        comodel_name="l10n_pe.res.city.district",
        string="Distrito",
    )
    l10n_pe_asset_city = fields.Char(string="Ciudad")
    l10n_pe_asset_registration_note = fields.Text(
        string="Casilla de comentarios para el activo de alta",
    )

    @api.onchange("l10n_pe_asset_district_id")
    def _onchange_l10n_pe_asset_district_id(self):
        """Al elegir el distrito, se autocompleta su provincia (como en contactos)."""
        if self.l10n_pe_asset_district_id:
            self.l10n_pe_asset_province_id = self.l10n_pe_asset_district_id.city_id

    @api.onchange("l10n_pe_asset_province_id")
    def _onchange_l10n_pe_asset_province_id(self):
        """Si la provincia cambia y ya no corresponde al distrito, se limpia el distrito."""
        district = self.l10n_pe_asset_district_id
        if (
            self.l10n_pe_asset_province_id
            and district.city_id
            and district.city_id != self.l10n_pe_asset_province_id
        ):
            self.l10n_pe_asset_district_id = False
