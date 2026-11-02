# -*- coding: utf-8 -*-
import logging

from odoo.addons.stock_kardex_adjustment_jeal.hooks import mark_existing_moves

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    mark_existing_moves(cr)
    cr.execute("SELECT kardex_adjustment_type, count(*) FROM account_move "
               "WHERE kardex_adjustment GROUP BY 1")
    _logger.info('Asientos marcados como ajuste por kardex: %s', cr.fetchall())
