import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Al instalar el módulo, propaga el product_id de las líneas originales
    hacia las líneas de sus asientos de destino (AED) ya existentes.

    Lógica de vinculación:
      - account.move.destination_move_id  enlaza el asiento origen con su AED
      - account.move.line.name            es el único campo compartido entre
                                          línea origen y línea AED

    Cada línea origen genera 2 líneas en el AED (débito destino + contrapartida),
    ambas con el mismo 'name' → ambas reciben el mismo product_id, correcto.

    Se usa SQL directo para no disparar recálculos del ORM sobre asientos
    publicados (impuestos, conciliaciones, etc.).

    Solo actualiza líneas AED donde product_id IS NULL para no pisar nada.
    En caso de ambigüedad (mismo nombre, distintos productos en el origen),
    se toma el de mayor product_id para ser determinista (DISTINCT ON).
    """
    _logger.info(
        "account_cust_ext: iniciando propagación de product_id "
        "a líneas de asientos de destino existentes..."
    )

    env.cr.execute("""
        UPDATE account_move_line aed_line
        SET product_id = matched.product_id
        FROM (
            SELECT DISTINCT ON (aed_line_inner.id)
                aed_line_inner.id   AS aed_line_id,
                origin_line.product_id
            FROM account_move origin_move
            JOIN account_move origin_aed
                ON origin_aed.id = origin_move.destination_move_id
            JOIN account_move_line aed_line_inner
                ON aed_line_inner.move_id = origin_aed.id
               AND aed_line_inner.product_id IS NULL
            JOIN account_move_line origin_line
                ON origin_line.move_id = origin_move.id
               AND origin_line.name = aed_line_inner.name
               AND origin_line.product_id IS NOT NULL
            ORDER BY aed_line_inner.id, origin_line.product_id DESC
        ) matched
        WHERE aed_line.id = matched.aed_line_id
    """)

    updated = env.cr.rowcount
    _logger.info(
        "account_cust_ext: %d líneas de asientos de destino actualizadas con product_id.",
        updated,
    )
