from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Marca como "Última ejecución" la más reciente calculada, para que los menús
    Resumen por par y Detalle (filtrados por defecto en la última) no queden vacíos
    hasta la próxima generación."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    last = env['ic.reconciliation.run'].search([('state', '=', 'done')], order='id desc', limit=1)
    last.write({'is_last': True})
