import ast
from datetime import datetime

from odoo import models
from odoo.tools.float_utils import float_round


class SireSaleBase(models.AbstractModel):
    """Override de sire.sale.base (l10n_pe_sire_sunat) con dos customizaciones:

    1. ``_select_sire_sale``: agrega la columna ``move_type`` (necesaria para
       el procesamiento posterior), aplica LPAD al ``invoice_correlative`` en
       documentos 01/02/03/07/08, y neutraliza la columna ``detraction``.

    2. ``_process_query_results``: añade tolerancia de 2 céntimos al
       ``s_base_og`` y reclasifica las notas de crédito ``out_refund`` que
       referencian a una factura de un período anterior, moviendo
       ``s_base_og``/``s_tax_og`` a las columnas ``ogd`` correspondientes.

    Compatibilidad Odoo 18:
        En v18 el upstream `_select_sire_sale` mantiene las mismas columnas
        que en v16 con dos diferencias: no expone ``move_type`` (lo añadimos
        nosotros) y devuelve ``'TieneDetraccion'`` en la columna detraction
        (nosotros la dejamos vacía intencionalmente). La firma de los métodos
        y la estructura de ``_from_sire_sale`` no cambiaron, por lo que este
        override sigue siendo compatible sin cambios de lógica.
    """
    _inherit = 'sire.sale.base'

    def _select_sire_sale(self):
        return f"""
            account_move.id AS move_id,
            LEFT(COALESCE('{self.company_id.vat}', ''), 11) AS company_vat,
            LEFT(COALESCE(company.name, ''), 1500) AS company_name,
            LEFT(COALESCE('{self.year}{self.month}', ''), 6) AS period,
            LEFT(COALESCE(TO_CHAR(account_move.invoice_date, 'DD/MM/YYYY'), ''), 10) AS invoice_date,
            LEFT(COALESCE(document_type.code, ''), 2) AS document_type_code,
            LEFT(COALESCE(REPLACE(REPLACE(REPLACE(account_move.name, '/', ''), ' ', ''), '-', ''), ''), 40) AS invoice_name,
            LEFT(COALESCE(
                (
                    SELECT account_move_line.ple_correlative
                    FROM account_move_line AS account_move_line
                    INNER JOIN account_account AS account_account ON account_move_line.account_id = account_account.id
                    WHERE
                        account_move_line.move_id = account_move.id
                        AND account_account.account_type = 'asset_receivable'
                    ORDER BY
                        ABS(
                            EXTRACT(YEAR FROM AGE(account_move_line.date_maturity, account_move.invoice_date)) * 12 +
                            EXTRACT(MONTH FROM AGE(account_move_line.date_maturity, account_move.invoice_date))
                        ) DESC
                    LIMIT 1
                ), ''
            ), 10) AS invoice_line_correlative,
            LEFT(COALESCE(SPLIT_PART(REPLACE(account_move.name, ' ', ''), '-', 1), ''), 20) AS invoice_serie,
            CASE
                WHEN document_type.code IN ('01', '02', '03', '07', '08') and account_move.name IS NOT NULL THEN
                    LPAD(LEFT(COALESCE(SPLIT_PART(REPLACE(account_move.name, ' ', ''), '-', 2), ''), 20), 8, '0')
                ELSE
                    LEFT(COALESCE(SPLIT_PART(REPLACE(account_move.name, ' ', ''), '-', 2), ''), 20)
            END AS invoice_correlative,
            LEFT(COALESCE(identification_type.l10n_pe_vat_code, ''), 1) AS partner_identification_code,
            LEFT(COALESCE(partner.vat, ''), 15) AS partner_vat,
            validate_string(partner.name, 1500) AS partner_name,
            get_tax(account_move.id, account_move.move_type, COALESCE(document_type.code, '')) AS tax_data,
            LEFT(COALESCE(currency.name, ''), 3) AS currency_name,
            CASE
                WHEN currency.name = 'PEN' THEN
                    NULL
                ELSE
                    ROUND(account_move.exchange_rate, 3)
            END AS exchange_rate,
            LEFT(COALESCE(TO_CHAR(account_move.origin_invoice_date, 'DD/MM/YYYY'), ''), 10) AS origin_invoice_date,
            LEFT(COALESCE(origin_document_type.code, ''), 2) AS origin_document_type_code,
            LEFT(COALESCE(SPLIT_PART(REPLACE(account_move.origin_number, ' ', ''), '-', 1), ''), 20) AS origin_number_serie,
            LEFT(COALESCE(SPLIT_PART(REPLACE(account_move.origin_number, ' ', ''), '-', 2), ''), 20) AS origin_number_correlative,
            CASE WHEN account_move.bool_pay_invoice IS NOT NULL THEN '1' ELSE '' END AS bool_pay_invoice,
            LEFT(COALESCE(account_move.ple_state, ''), 1) AS ple_state,
            account_move.move_type AS move_type,
            CASE WHEN account_move.l10n_pe_edi_operation_type IN ('1001', '1002', '1003', '1004') THEN '' ELSE '' END AS detraction
        """

    def _parse_date(self, date_str):
        if date_str:
            return datetime.strptime(date_str, '%d/%m/%Y')
        return None

    def _process_query_results(self):
        query_results = self._execute_query_sire_sale()
    
        move_ids = [r['move_id'] for r in query_results if r.get('move_id')]
        moves_by_id = {m.id: m for m in self.env['account.move'].browse(move_ids)}
    
        for line_result in query_results:
            tax_data = ast.literal_eval(line_result['tax_data'])
            s_base_og = float_round(tax_data[1] or 0.0, precision_digits=2)
            # Tolerancia de 2 céntimos: cantidades residuales por redondeo
            # se neutralizan para no figurar como base gravada en SIRE.
            if abs(s_base_og) <= 0.02:
                s_base_og = 0.0
            line_result.update({
                's_base_exp': tax_data[0],
                's_base_og': s_base_og,
                's_base_ogd': tax_data[2],
                's_tax_og': tax_data[3],
                's_tax_ogd': tax_data[4],
                's_base_oe': tax_data[5],
                's_base_ou': tax_data[6],
                's_tax_isc': tax_data[7],
                's_tax_icbp': tax_data[8],
                's_base_ivap': tax_data[9],
                's_tax_ivap': tax_data[10],
                's_tax_other': tax_data[11],
                'amount_total': sum(tax_data[:12]),
            })
    
            move = moves_by_id.get(line_result.get('move_id'))
            if move:
                rnd = move.currency_id.rounding or 0.01
                for field_name, invoice_value in (
                    ('s_tax_og',  move.amount_tax),
                    ('s_base_og', move.amount_untaxed),
                ):
                    calc = line_result[field_name]
                    if abs(invoice_value - calc) <= rnd and abs(invoice_value) < rnd:
                        line_result[field_name] = 0.0
                # Recalcular total con los valores ya snappeados
                line_result['amount_total'] = sum(
                    line_result[k] for k in (
                        's_base_exp', 's_base_og', 's_base_ogd', 's_tax_og', 's_tax_ogd',
                        's_base_oe', 's_base_ou', 's_tax_isc', 's_tax_icbp',
                        's_base_ivap', 's_tax_ivap', 's_tax_other',
                    )
                )
    
        # Reclasificación de notas de crédito (out_refund) cuyo documento
        # origen pertenece a un período (mes o año) anterior: SUNAT exige
        # reportarlas en las columnas "ogd" (gravadas de períodos
        # anteriores) en lugar de "og".
        for val in query_results:
            val['s_base_ogd'] = 0.0
            val['s_tax_ogd'] = 0.0
    
            invoice_date = self._parse_date(val['invoice_date'])
            origin_invoice_date = self._parse_date(val['origin_invoice_date'])
    
            if (
                invoice_date is not None
                and origin_invoice_date is not None
                and val['move_type'] == 'out_refund'
                and (
                    origin_invoice_date.month < invoice_date.month
                    or origin_invoice_date.year < invoice_date.year
                )
            ):
                val['s_base_ogd'] = val['s_base_og']
                val['s_tax_ogd'] = val['s_tax_og']
                val['s_base_og'] = 0.0
                val['s_tax_og'] = 0.0
    
            val.pop('move_id', None)
    
        return query_results
