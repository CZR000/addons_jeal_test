import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    env.cr.execute(
        """
        UPDATE stock_valuation_layer svl
        SET standard_price = COALESCE(
            pp.standard_price -> svl.company_id::text,
            to_jsonb(0.0)
        )::float
        FROM (
            SELECT product_id, company_id, MAX(id) as max_id
            FROM stock_valuation_layer
            WHERE lot_id IS NULL
            GROUP BY product_id, company_id
        ) last_svl
        JOIN product_product pp ON pp.id = last_svl.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE svl.id = last_svl.max_id
        AND (pt.lot_valuated IS NULL OR pt.lot_valuated = FALSE)
    """
    )
    products_updated = env.cr.rowcount
    _logger.info(f"Updated {products_updated} SVLs for products without lot valuation.")

    env.cr.execute(
        """
        UPDATE stock_valuation_layer svl
        SET standard_price = COALESCE(
            sl.standard_price -> svl.company_id::text,
            pp.standard_price -> svl.company_id::text,
            to_jsonb(0.0)
        )::float
        FROM (
            SELECT lot_id, company_id, MAX(id) as max_id
            FROM stock_valuation_layer
            WHERE lot_id IS NOT NULL
            GROUP BY lot_id, company_id
        ) last_svl
        JOIN stock_lot sl ON sl.id = last_svl.lot_id
        JOIN product_product pp ON pp.id = sl.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE svl.id = last_svl.max_id
        AND pt.lot_valuated = TRUE
    """
    )
    lots_updated = env.cr.rowcount
    _logger.info(f"Updated {lots_updated} SVLs for lots with lot valuation.")
