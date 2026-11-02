/** @odoo-module **/
//
// Odoo 18: el frontend de account_reports se reescribió de un widget jQuery
// (`accountReportsWidget`) a un componente Owl 2 (`AccountReportFilters`).
// Esta versión usa el sistema de patches actual (`@web/core/utils/patch`) y
// reemplaza la inyección DOM con jQuery por una herencia de plantilla Owl
// (ver `account_reports_journals_select_all.xml`).
//
// Compatibilidad con el override Python de `_init_options_journals`:
//   * Al hacer click en "Seleccionar todos" se ponen `selected = true` en
//     todos los diarios y se inserta el flag
//     `__all_journals_explicitly_selected = true` en options. El backend usa
//     ese flag para preservar la selección completa en el siguiente reload.
//   * Al hacer click en "Deseleccionar todos" se ponen `selected = false`
//     y se inserta `__all_journals_deselected = true` para distinguir esta
//     intención de "no se ha tocado el filtro".
//   * Al hacer click en un diario individual (override de `selectJournal`)
//     se limpia el flag `__all_journals_explicitly_selected` para que el
//     backend trate la siguiente carga como una selección manual.

import { patch } from "@web/core/utils/patch";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

patch(AccountReportFilters.prototype, {
    /**
     * Selecciona todos los diarios disponibles y desactiva cualquier grupo
     * de diarios. Inserta los flags que el override Python espera.
     */
    selectAllJournals() {
        const options = this.controller.options;
        if (!options.journals) {
            return;
        }

        for (const journal of options.journals) {
            if (journal.model === "account.journal") {
                journal.selected = true;
            } else if (journal.model === "account.journal.group") {
                journal.selected = false;
            }
        }

        options.__all_journals_explicitly_selected = true;
        delete options.__all_journals_deselected;
        delete options.__journal_group_action;

        this.applyFilters("journals");
    },

    /**
     * Deselecciona todos los diarios (en la semántica de Odoo, esto equivale
     * a "incluir todos" porque ningún diario seleccionado significa "sin
     * filtro"). Insertamos `__all_journals_deselected` para diferenciar
     * intención del usuario vs estado inicial.
     */
    deselectAllJournals() {
        const options = this.controller.options;
        if (!options.journals) {
            return;
        }

        for (const journal of options.journals) {
            journal.selected = false;
        }

        delete options.__all_journals_explicitly_selected;
        options.__all_journals_deselected = true;
        delete options.__journal_group_action;

        this.applyFilters("journals");
    },

    /**
     * Override del handler individual: si el usuario hace click sobre un
     * diario después de un "Seleccionar todos", limpiamos el flag para que
     * el backend deje de forzar la preservación de la selección completa.
     */
    selectJournal(journal) {
        if (
            journal.model === "account.journal"
            && this.controller.options.__all_journals_explicitly_selected
        ) {
            delete this.controller.options.__all_journals_explicitly_selected;
        }
        return super.selectJournal(journal);
    },
});
