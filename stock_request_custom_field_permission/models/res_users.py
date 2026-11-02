from odoo import models, api
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.constrains("groups_id")
    def _check_exclusive_groups(self):
        group_edit = self.env.ref(
            "stock_request_custom_field_permission.group_edit_comment_stock_request"
        )
        group_view = self.env.ref(
            "stock_request_custom_field_permission.group_view_comment_stock_request"
        )
        for user in self:
            if group_edit in user.groups_id and group_view in user.groups_id:
                raise ValidationError(
                    "No puedes estar en los grupos de 'Permitir editar comentarios' y 'Permitir ver comentarios' al mismo tiempo."
                )
