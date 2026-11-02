from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    ple_book_code = fields.Selection(
        selection=[
            ('0', 'Apertura'),
            ('1', 'Caja'),
            ('2', 'Bancos'),
            ('5', 'Registro de Compras'),
            ('13', 'Almacen / Inventarios'),
            ('14', 'Registro de Ventas'),
            ('31', 'Planillas'),
        ],
        string='Codigo Subdiario PLE',
        help='Codigo CL que aparecera en la columna "CL" del reporte '
             'Libro Diario Formato 5.1. Se usa como agrupador y para '
             'reiniciar el correlativo del asiento por mes.',
    )
