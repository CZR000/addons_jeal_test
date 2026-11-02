# -*- coding: utf-8 -*-

# Columnas de campos related almacenados sobre tablas grandes: crearlas antes de
# instalar evita que Odoo las calcule registro por registro (quedan en NULL,
# que el ORM lee como «sin ajuste»).
PRECREATED_COLUMNS = [
    ('account_move', 'kardex_adjusted_stock_move_id', 'int4'),
    ('account_move_line', 'kardex_adjustment', 'boolean'),
    ('account_move_line', 'kardex_adjustment_type', 'varchar'),
]


def add_columns(cr):
    for table, column, column_type in PRECREATED_COLUMNS:
        cr.execute('ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s %s' % (table, column, column_type))


def mark_existing_moves(cr):
    """Marca los asientos de ajuste ya registrados (2.3): el asiento principal
    con el tipo del ajuste, el complementario con «Destino 61» y las
    reversiones con el tipo del asiento que revierten."""
    cr.execute("""
        UPDATE account_move am
           SET kardex_adjustment = TRUE,
               kardex_adjustment_type = l.adjustment_type,
               kardex_adjustment_run_id = l.run_id,
               kardex_adjusted_layer_id = l.adjusted_layer_id,
               kardex_adjusted_stock_move_id = svl.stock_move_id
          FROM stock_kardex_adjustment_line l
          JOIN stock_valuation_layer svl ON svl.id = l.adjusted_layer_id
         WHERE am.id = l.move_id
    """)
    cr.execute("""
        UPDATE account_move am
           SET kardex_adjustment = TRUE,
               kardex_adjustment_type = l.adjustment_type || '_61',
               kardex_adjustment_run_id = l.run_id,
               kardex_adjusted_layer_id = l.adjusted_layer_id,
               kardex_adjusted_stock_move_id = svl.stock_move_id
          FROM stock_kardex_adjustment_line l
          JOIN stock_valuation_layer svl ON svl.id = l.adjusted_layer_id
         WHERE am.id = l.fx_move_id
    """)
    cr.execute("""
        UPDATE account_move am
           SET kardex_adjustment = TRUE,
               kardex_adjustment_type = CASE WHEN am.reversed_entry_id = l.fx_move_id
                                             THEN l.adjustment_type || '_61'
                                             ELSE l.adjustment_type END,
               kardex_adjustment_run_id = l.run_id,
               kardex_adjusted_layer_id = l.adjusted_layer_id,
               kardex_adjusted_stock_move_id = svl.stock_move_id
          FROM stock_kardex_adjustment_line_reversal_rel rel
          JOIN stock_kardex_adjustment_line l ON l.id = rel.line_id
          JOIN stock_valuation_layer svl ON svl.id = l.adjusted_layer_id
         WHERE am.id = rel.move_id
    """)
    cr.execute("""
        UPDATE account_move_line aml
           SET kardex_adjustment = am.kardex_adjustment,
               kardex_adjustment_type = am.kardex_adjustment_type
          FROM account_move am
         WHERE aml.move_id = am.id
           AND am.kardex_adjustment
    """)


def pre_init_hook(env):
    add_columns(env.cr)
