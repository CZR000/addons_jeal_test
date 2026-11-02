# -*- coding: utf-8 -*-
from odoo.addons.stock_kardex_adjustment_jeal.hooks import add_columns


def migrate(cr, version):
    add_columns(cr)
