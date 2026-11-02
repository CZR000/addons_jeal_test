import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _post_init_hook(cr, registry):
    try:
        _logger.info("Iniciando post-init-hook para crear diarios y grupos contables")
        _create_destination_account_journal(cr, registry)
        _create_destination_account_group(cr, registry)
        _logger.info("Post-init-hook completado exitosamente")
    except Exception as e:
        _logger.error("Error durante la ejecución del post-init-hook: %s", str(e))
        raise


def _create_destination_account_journal(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        peru = env.ref("base.pe", raise_if_not_found=False)
        if not peru:
            _logger.warning("No se encontró el país Perú en la base de datos")
            return

        all_companies = (
            env["res.company"]
            .sudo()
            .search([])
            .filtered(lambda c: c.country_id and c.country_id == peru)
        )

        _logger.info("Se encontraron %d compañías peruanas", len(all_companies))

        for company in all_companies:
            try:
                # Verificar si ya existe un diario similar
                existing_journal = (
                    env["account.journal"]
                    .sudo()
                    .search(
                        [("code", "=", "AED"), ("company_id", "=", company.id)], limit=1
                    )
                )

                if existing_journal:
                    _logger.info(
                        "El diario AED ya existe para la compañía %s (ID: %d)",
                        company.name,
                        company.id,
                    )
                    continue

                journal = (
                    env["account.journal"]
                    .sudo()
                    .create(
                        {
                            "name": "ASIENTOS DE DESTINO",
                            "code": "AED",
                            "type": "general",
                            "move_type": "M",
                            "company_id": company.id,
                        }
                    )
                )
                company.sudo().write({"destination_account_journal_id": journal.id})
                _logger.info(
                    "Diario AED creado exitosamente para la compañía %s (ID: %d)",
                    company.name,
                    company.id,
                )
            except Exception as e:
                _logger.error(
                    "Error al crear el diario para la compañía %s (ID: %d): %s",
                    company.name,
                    company.id,
                    str(e),
                )

    except Exception as e:
        _logger.error(
            "Error general en _create_destination_account_journal: %s", str(e)
        )
        raise


def _create_destination_account_group(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        peru = env.ref("base.pe", raise_if_not_found=False)
        if not peru:
            _logger.warning("No se encontró el país Perú en la base de datos")
            return

        all_companies = (
            env["res.company"]
            .sudo()
            .search([])
            .filtered(lambda c: c.country_id and c.country_id == peru)
        )

        _logger.info(
            "Creando grupos contables para %d compañías peruanas", len(all_companies)
        )

        for company in all_companies:
            try:
                # Verificar si ya existe un grupo similar
                existing_group = (
                    env["account.group"]
                    .sudo()
                    .search(
                        [
                            ("code_prefix_start", "=", "91"),
                            ("code_prefix_end", "=", "97"),
                            ("company_id", "=", company.id),
                        ],
                        limit=1,
                    )
                )

                if existing_group:
                    _logger.info(
                        "El grupo contable ya existe para la compañía %s (ID: %d)",
                        company.name,
                        company.id,
                    )
                    continue

                env["account.group"].sudo().create(
                    {
                        "name": "Contabilidad análitica de explotación: Costos de producción y gastos por función",
                        "code_prefix_start": "91",
                        "code_prefix_end": "97",
                        "company_id": company.id,
                    }
                )
                _logger.info(
                    "Grupo contable creado exitosamente para la compañía %s (ID: %d)",
                    company.name,
                    company.id,
                )
            except Exception as e:
                _logger.error(
                    "Error al crear el grupo contable para la compañía %s (ID: %d): %s",
                    company.name,
                    company.id,
                    str(e),
                )

    except Exception as e:
        _logger.error("Error general en _create_destination_account_group: %s", str(e))
        raise
