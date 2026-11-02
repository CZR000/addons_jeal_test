from odoo import _, api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    custom_po_report_style = fields.Boolean(
        string="Custom Purchase Report Style",
        help=(
            "If enabled, the purchase order report will use "
            "custom styling for order number and totals section."
        ),
    )
