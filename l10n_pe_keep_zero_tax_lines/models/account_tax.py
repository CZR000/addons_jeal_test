from odoo import models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    def _prepare_base_line_tax_repartition_grouping_key(
        self, base_line, base_line_grouping_key, tax_data, tax_rep_data,
    ):
        """Fuerza __keep_zero_line=True cuando la compañía es peruana.

        En Odoo 18 el método _prepare_tax_lines descarta las líneas de impuesto
        cuyo importe agrupado (amount_currency y balance) queda en 0. Esto
        rompe el PLE/Registro de Ventas peruano, que necesita la línea de la
        cuenta de impuesto (4011100) con sus tags (+S_TAX_OG) aunque el neto
        sea 0 — típico en facturas con Descuento y Anticipo que netean.

        Odoo previó este caso con el flag __keep_zero_line en el grouping_key
        (por defecto False). Aquí lo activamos solo para compañías peruanas.
        """
        results = super()._prepare_base_line_tax_repartition_grouping_key(
            base_line, base_line_grouping_key, tax_data, tax_rep_data,
        )
        if self._l10n_pe_should_keep_zero_tax_line(base_line, tax_data):
            results['__keep_zero_line'] = True
        return results

    def _l10n_pe_should_keep_zero_tax_line(self, base_line, tax_data):
        """Devuelve True si la línea de impuesto debe conservarse en 0.

        Regla: si la compañía del asiento es peruana, preservar. Se aísla en
        un helper para que otras localizaciones o customs puedan extender la
        condición (p. ej. limitar a ciertos tax_group) sin reescribir el
        override principal.
        """
        company = self._l10n_pe_get_base_line_company(base_line, tax_data)
        return bool(company and company.country_id.code == 'PE')

    @staticmethod
    def _l10n_pe_get_base_line_company(base_line, tax_data):
        """Obtiene la compañía asociada a la base_line.

        base_line no expone company_id directamente. Se intenta primero por
        el record (usualmente account.move.line), luego por el impuesto.
        """
        record = base_line.get('record')
        if record and hasattr(record, 'company_id') and record.company_id:
            return record.company_id
        tax = tax_data.get('tax')
        if tax and tax.company_id:
            return tax.company_id
        return False
