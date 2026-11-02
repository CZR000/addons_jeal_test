import logging

from odoo import fields

_logger = logging.getLogger(__name__)

SKIP_PARAM = "purchase_stock_price_diff_control.skip_install_repair"


def post_init_hook(env):
    """Programa la corrección del histórico, sin ejecutarla durante la instalación.

    En bases grandes (esta tiene 148k capas de valorización y 1.9M de apuntes)
    corregir dentro de la propia instalación alarga la transacción hasta que el
    worker se queda sin tiempo o sin memoria y la instalación se pierde entera.

    Por eso aquí no se corrige nada: sólo se activa el cron
    ``ir_cron_pdiff_repair``, que trabaja por lotes, hace commit de cada uno y se
    desactiva solo al terminar. La corrección sigue siendo automática -no hay que
    hacer nada a mano-, pero la instalación termina en segundos y es reversible.

    Para no corregir nada en absoluto, fijar el parámetro de sistema
    ``SKIP_PARAM`` antes de instalar y lanzarlo luego desde
    Inventario > Informes > Corregir ajustes de precio duplicados.
    """
    if env["ir.config_parameter"].sudo().get_param(SKIP_PARAM):
        _logger.info(
            "purchase_stock_price_diff_control: corrección automática omitida (%s activo).",
            SKIP_PARAM,
        )
        return

    cron = env.ref(
        "purchase_stock_price_diff_control.ir_cron_pdiff_repair",
        raise_if_not_found=False,
    )
    if not cron:
        _logger.warning(
            "purchase_stock_price_diff_control: no se encontró el cron de corrección; "
            "lánzala a mano desde el asistente."
        )
        return

    cron.sudo().write({"active": True, "nextcall": fields.Datetime.now()})
    _logger.info(
        "purchase_stock_price_diff_control: instalado. La corrección del histórico "
        "queda programada en el cron '%s', que la hará por lotes y se desactivará "
        "solo al terminar.",
        cron.name,
    )
