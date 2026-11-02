from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class StockRequest(models.Model):
    _inherit = "stock.request"

    # Campo editable para los usuarios que tengan el permiso
    comment_editable = fields.Text(
        string="Comentario (Editable)",
        help="Campo de comentarios que solo puede ser editado por usuarios con permisos específicos.",
        default="",
        translate=False,
        required=False,
        tracking=True,
    )

    # Campo de solo lectura para todos los usuarios, sincronizado con el campo editable
    comment_readonly = fields.Text(
        string="Comentario (Solo lectura)",
        help="Campo de comentarios de solo lectura para todos los usuarios.",
        compute="_compute_comment_readonly",
        readonly=True,
        store=False,
    )

    # Método para sincronizar el campo 'comment_readonly' con 'comment_editable'
    @api.depends("comment_editable")
    def _compute_comment_readonly(self):
        for record in self:
            record.comment_readonly = record.comment_editable
