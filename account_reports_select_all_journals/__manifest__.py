{
    'name': 'Account Reports - Select All Journals',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Add Select All / Deselect All buttons for journals filter in accounting reports',
    'description': """
        This module adds "Select All" and "Deselect All" buttons
        to the journals filter in accounting reports, making it easier
        to manage journal selection when you have many journals.

        Odoo 18: el frontend de account_reports fue reescrito de un widget
        jQuery (`accountReportsWidget`) a componentes Owl 2 puros. Este
        módulo extiende ahora `AccountReportFilters` vía
        `@web/core/utils/patch` y hereda la plantilla
        `account_reports.AccountReportFilterJournal` para inyectar los dos
        botones dentro del Dropdown.
    """,
    'author': 'Jimmy Technologies',
    'website': 'https://www.jimmytechnologies.com',
    'depends': ['account_reports'],
    'assets': {
        'web.assets_backend': [
            'account_reports_select_all_journals/static/src/scss/account_reports_journals_select_all.scss',
            'account_reports_select_all_journals/static/src/xml/account_reports_journals_select_all.xml',
            'account_reports_select_all_journals/static/src/js/account_reports_journals_select_all.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
