from odoo import models, _


class AccountReportSelectAllJournals(models.Model):
    """Override del handler que construye el filtro de diarios en options.

    Cuando el frontend marca el flag ``__all_journals_explicitly_selected``
    (porque el usuario hizo click en "Seleccionar todos"), preservamos la
    selección completa al recargar. Sin este override, Odoo descarta la
    selección cuando TODOS los diarios están marcados (lo trata como "no se
    eligió ninguno" → incluir todos).

    Compatibilidad Odoo 18:
        Firma de ``_init_options_journals(self, options, previous_options,
        additional_journals_domain=None)`` confirmada idéntica en v18 enterprise
        (``account_reports/models/account_report.py:256``). Las claves
        ``options['journals']``, ``options['name_journal_group']``,
        ``model``, ``selected``, ``__journal_group_action`` siguen iguales.
    """
    _inherit = 'account.report'

    def _init_options_journals(self, options, previous_options, additional_journals_domain=None):
        if not self.filter_journals:
            return

        # Capturamos el flag ANTES de llamar a super() porque el método base
        # consume previous_options y podría limpiar claves auxiliares.
        all_journals_flag = bool(
            previous_options and previous_options.get('__all_journals_explicitly_selected')
        )

        super()._init_options_journals(options, previous_options, additional_journals_domain)

        if not (all_journals_flag and options.get('journals')):
            return

        # Verificamos que en previous_options TODOS los diarios estaban
        # seleccionados. Si el usuario deseleccionó alguno entre tanto, el
        # frontend ya habrá limpiado el flag, pero hacemos defensa en
        # profundidad por si se llamó desde RPC sin pasar por la UI.
        available_journals = [
            j for j in options['journals'] if j.get('model') == 'account.journal'
        ]

        if not (previous_options and previous_options.get('journals')):
            return

        prev_selected = [
            j for j in previous_options['journals']
            if j.get('model') == 'account.journal' and j.get('selected')
        ]

        if len(prev_selected) != len(available_journals):
            return

        # Forzamos la selección completa: marcamos todos los diarios y
        # desmarcamos todos los grupos (para evitar que el indicador "Grupo X
        # seleccionado" muestre algo incorrecto en la UI).
        for journal_option in options['journals']:
            if journal_option.get('model') == 'account.journal':
                journal_option['selected'] = True
            elif journal_option.get('model') == 'account.journal.group':
                journal_option['selected'] = False

        journal_count = len(available_journals)
        options['name_journal_group'] = _("Todos los diarios (%s)") % journal_count

        # Re-insertamos el flag en las nuevas options para que la próxima
        # carga lo reciba de vuelta y mantenga el ciclo.
        options['__all_journals_explicitly_selected'] = True
