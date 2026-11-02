import logging
from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..reports.report_inv_bal_0301 import InvBal31ReportExcel

_logger = logging.getLogger(__name__)


class PleReportInvBalBook0301(models.Model):
    """Formato 3.1 (Balance General) del Libro de Inventarios y Balances."""

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_01(self):
        """Formato 3.1 - Balance General."""
        return self._generate_single('01')

    def _prepare_report_01(self):
        self.ensure_one()
        return InvBal31ReportExcel(self, self._get_data_01())

    # ------------------------------------------------------------------
    # DATA - Formato 3.1 Balance General
    # ------------------------------------------------------------------
    #
    # La tabla es la de siempre (mismas secciones, titulos, totales y
    # filas en blanco). Solo las lineas de detalle y los importes salen
    # del reporte contable "Balance de situacion" de Odoo al `date_end`:
    #   ACTIVO CORRIENTE     <- lineas de "Activos corrientes"
    #   ACTIVO NO CORRIENTE  <- demas lineas de Activos
    #   PASIVO CORRIENTE     <- lineas de "Pasivos corrientes"
    #   PASIVO NO CORRIENTE  <- demas lineas de Pasivos
    #   PATRIMONIO NETO      <- lineas de Patrimonio (un nivel mas si la
    #                           linea agrupa otras)
    # Los totales toman el importe de la linea equivalente del reporte.

    # Codigos de las lineas del Balance de situacion estandar de Odoo.
    BS_CURRENT_ASSETS_CODES = ('CA',)
    BS_CURRENT_LIABILITIES_CODES = ('CL',)

    # Estado de situacion financiera (PE) configurado en la base de datos:
    # reporte plano (sin lineas padre) con codigos ESF_xxx. Las lineas de
    # detalle de cada seccion son las que estan entre su encabezado y su
    # total, en el orden del reporte.
    ESF_CODES = {
        'activo_corriente': ('ESF_002', 'ESF_012'),
        'activo_no_corriente': ('ESF_013', 'ESF_021'),
        'total_activo': 'ESF_022',
        'pasivo_corriente': ('ESF_024', 'ESF_035'),
        'pasivo_no_corriente': ('ESF_036', 'ESF_041'),
        'total_pasivo': 'ESF_042',
        'patrimonio': ('ESF_045', 'ESF_054'),
        'total_pasivo_patrimonio': 'ESF_055',
    }
    ESF_REQUIRED_CODES = (
        'ESF_002', 'ESF_012', 'ESF_013', 'ESF_021', 'ESF_022',
        'ESF_024', 'ESF_035', 'ESF_036', 'ESF_041', 'ESF_042',
        'ESF_045', 'ESF_054', 'ESF_055',
    )

    def _get_data_01_esf(self, lines):
        """Balance General a partir del Estado de situacion financiera (PE)
        de la base de datos (codigos ESF_xxx). Misma tabla de siempre; las
        lineas de detalle y los importes son los del reporte."""
        codes = self.ESF_CODES
        index = {line.get('_code'): i for i, line in enumerate(lines)}
        value = self._report_line_value

        def amount(code):
            return value(lines[index[code]])

        def details(start_code, end_code):
            return [
                ('line', line.get('name') or '', value(line))
                for line in lines[index[start_code] + 1:index[end_code]]
            ]

        ac_start, ac_end = codes['activo_corriente']
        anc_start, anc_end = codes['activo_no_corriente']
        activo = [
            ('section', 'ACTIVO', None),
            ('section', 'ACTIVO CORRIENTE', None),
            *details(ac_start, ac_end),
            ('total', 'TOTAL ACTIVO CORRIENTE', amount(ac_end)),
            ('blank', '', None),
            ('section', 'ACTIVO NO CORRIENTE', None),
            *details(anc_start, anc_end),
            ('total', 'TOTAL ACTIVO NO CORRIENTE', amount(anc_end)),
            ('blank', '', None),
            ('total', 'TOTAL ACTIVO', amount(codes['total_activo'])),
        ]

        pc_start, pc_end = codes['pasivo_corriente']
        pnc_start, pnc_end = codes['pasivo_no_corriente']
        pn_start, pn_end = codes['patrimonio']
        # Lineas entre TOTAL PASIVO y PATRIMONIO NETO (Contingencias,
        # Interes minoritario), igual que en el reporte.
        between = details(codes['total_pasivo'], pn_start)
        pasivo = [
            ('section', 'PASIVO Y PATRIMONIO', None),
            ('section', 'PASIVO CORRIENTE', None),
            *details(pc_start, pc_end),
            ('total', 'TOTAL PASIVO CORRIENTE', amount(pc_end)),
            ('blank', '', None),
            ('section', 'PASIVO NO CORRIENTE', None),
            *details(pnc_start, pnc_end),
            ('total', 'TOTAL PASIVO NO CORRIENTE', amount(pnc_end)),
            ('blank', '', None),
            ('total', 'TOTAL PASIVO', amount(codes['total_pasivo'])),
            *between,
            ('blank', '', None),
            ('section', 'PATRIMONIO NETO', None),
            *details(pn_start, pn_end),
            ('total', 'TOTAL PATRIMONIO NETO', amount(pn_end)),
            ('blank', '', None),
            ('total', 'TOTAL PASIVO Y PATRIMONIO NETO', amount(codes['total_pasivo_patrimonio'])),
        ]
        return {'activo': activo, 'pasivo': pasivo}

    def _get_data_01(self):
        """Devuelve la estructura del Balance General (columnas ACTIVO y
        PASIVO Y PATRIMONIO) con las lineas e importes del Balance de
        situacion al `date_end`.

        Retorna dict con:
            'activo':  lista de filas (tipo, label, valor)
            'pasivo':  lista de filas (tipo, label, valor)
        Tipos de fila: 'section', 'line', 'total', 'blank'.
        """
        self.ensure_one()
        lines = self._get_balance_sheet_lines()

        # Estado de situacion financiera de la compania (lineas planas con
        # codigos ESF_xxx): se toma cada seccion por sus codigos.
        if {line.get('_code') for line in lines} >= set(self.ESF_REQUIRED_CODES):
            return self._get_data_01_esf(lines)

        by_id = {line['id']: line for line in lines}
        children = defaultdict(list)
        roots = []
        for line in lines:
            parent = line.get('parent_id')
            if parent and parent in by_id:
                children[parent].append(line)
            else:
                roots.append(line)

        # Activos, Pasivos, Patrimonio (y Pasivos + Patrimonio).
        if len(roots) < 3:
            raise UserError(_(
                'El Balance de situación no devolvió las secciones Activos, '
                'Pasivos y Patrimonio al %s.'
            ) % self.date_end.strftime('%d/%m/%Y'))
        assets_root, liabilities_root, equity_root = roots[:3]
        value = self._report_line_value

        def detail(line):
            return ('line', line.get('name') or '', value(line))

        def split_current(root, codes):
            """(linea corriente, otras lineas) de Activos o Pasivos. La linea
            corriente es la del codigo estandar; si no existe, la primera
            que agrupa otras."""
            kids = children.get(root['id'], [])
            current = next((k for k in kids if k.get('_code') in codes), None)
            if current is None:
                current = next((k for k in kids if children.get(k['id'])), None)
            others = [k for k in kids if k is not current]
            return current, others

        def current_rows(current):
            if current is None:
                return [], 0.0
            kids = children.get(current['id'])
            return ([detail(k) for k in kids] if kids else [detail(current)]), value(current)

        # --- Columna ACTIVO ---
        ca, other_assets = split_current(assets_root, self.BS_CURRENT_ASSETS_CODES)
        ca_rows, tac = current_rows(ca)
        tanc = sum(value(k) for k in other_assets)

        activo = [
            ('section', 'ACTIVO', None),
            ('section', 'ACTIVO CORRIENTE', None),
            *ca_rows,
            ('total', 'TOTAL ACTIVO CORRIENTE', tac),
            ('blank', '', None),
            ('section', 'ACTIVO NO CORRIENTE', None),
            *[detail(k) for k in other_assets],
            ('total', 'TOTAL ACTIVO NO CORRIENTE', tanc),
            ('blank', '', None),
            ('total', 'TOTAL ACTIVO', value(assets_root)),
        ]

        # --- Columna PASIVO Y PATRIMONIO ---
        cl, other_liabilities = split_current(liabilities_root, self.BS_CURRENT_LIABILITIES_CODES)
        cl_rows, tpc = current_rows(cl)
        tpnc = sum(value(k) for k in other_liabilities)
        total_pasivo = value(liabilities_root)

        equity_rows = []
        for kid in children.get(equity_root['id'], []):
            grandkids = children.get(kid['id'])
            equity_rows.extend([detail(g) for g in grandkids] if grandkids else [detail(kid)])
        total_patrimonio = value(equity_root)

        if len(roots) > 3:
            total_pasivo_patrimonio = value(roots[3])
        else:
            total_pasivo_patrimonio = total_pasivo + total_patrimonio

        pasivo = [
            ('section', 'PASIVO Y PATRIMONIO', None),
            ('section', 'PASIVO CORRIENTE', None),
            *cl_rows,
            ('total', 'TOTAL PASIVO CORRIENTE', tpc),
            ('blank', '', None),
            ('section', 'PASIVO NO CORRIENTE', None),
            *[detail(k) for k in other_liabilities],
            ('total', 'TOTAL PASIVO NO CORRIENTE', tpnc),
            ('blank', '', None),
            ('total', 'TOTAL PASIVO', total_pasivo),
            ('blank', '', None),
            ('section', 'PATRIMONIO NETO', None),
            *equity_rows,
            ('total', 'TOTAL PATRIMONIO NETO', total_patrimonio),
            ('blank', '', None),
            ('total', 'TOTAL PASIVO Y PATRIMONIO NETO', total_pasivo_patrimonio),
        ]

        return {'activo': activo, 'pasivo': pasivo}

    def _get_balance_sheet_report(self):
        """Balance de situacion de Odoo; si existe una variante para el pais
        de la compania (p.ej. Peru), se usa esa."""
        root = self.env.ref('account_reports.balance_sheet', raise_if_not_found=False)
        if not root:
            raise UserError(_(
                'No se encontró el reporte "Balance de situación" '
                '(módulo account_reports).'
            ))
        country = self.company_id.account_fiscal_country_id
        if country:
            variant = self.env['account.report'].search([
                ('root_report_id', '=', root.id),
                ('country_id', '=', country.id),
            ], limit=1)
            if variant:
                return variant
        return root

    def _get_balance_sheet_lines(self):
        """Lineas del Balance de situacion al `date_end`, sin desplegar
        cuentas, en el orden del reporte. Solo las lineas propias del
        reporte (account.report.line)."""
        self.ensure_one()
        company = self.company_id
        report = self._get_balance_sheet_report().with_company(company).with_context(
            allowed_company_ids=[company.id],
        )
        fy_start = company.compute_fiscalyear_dates(self.date_end)['date_from']
        date_to = fields.Date.to_string(self.date_end)
        options = report.get_options(previous_options={
            'date': {
                'date_from': fields.Date.to_string(fy_start),
                'date_to': date_to,
                'filter': 'custom',
                'mode': 'single',
                'period_type': 'custom',
            },
            'comparison': {'filter': 'no_comparison', 'number_period': 1},
            'unfold_all': False,
            'unfolded_lines': [],
        })
        if (options.get('date') or {}).get('date_to') != date_to:
            raise UserError(_(
                'No se pudo calcular el Balance de situación al %s '
                '(el reporte devolvió la fecha %s).'
            ) % (self.date_end.strftime('%d/%m/%Y'),
                 (options.get('date') or {}).get('date_to') or '-'))

        result = []
        for line in report._get_lines(options):
            try:
                _markup, model, res_id = report._parse_line_id(line['id'])[-1]
            except (KeyError, IndexError, ValueError):
                continue
            if model == 'account.report.line':
                line['_code'] = self.env['account.report.line'].browse(res_id).code or ''
                result.append(line)
        return result

    @staticmethod
    def _report_line_value(line):
        """Importe de la primera columna de la linea del reporte."""
        columns = line.get('columns') or []
        if not columns:
            return 0.0
        try:
            return float(columns[0].get('no_format') or 0.0)
        except (TypeError, ValueError):
            return 0.0