{
    'name': 'Contact Carrier Field',
    'version': '18.0.3.0.2',
    'summary': 'Adds "Is Carrier" boolean field to contacts',
    'description': """
        Contact Carrier Field
        =====================
        Adds a boolean field 'Es Transportista' (is_carrier) to res.partner,
        available in form, list and search views (as filter and group by).
    """,
    'author': 'Empiria',
    'website': '',
    'category': 'Contacts',
    'license': 'LGPL-3',
    'depends': [
        'contacts',
        'account',
    ],
    'data': [
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/account_move_lines_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
