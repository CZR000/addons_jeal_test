/** @odoo-module **/
//
// Habilita el column-selector (checkboxes) en la lista de Journal Items
// embebida dentro del widget de Bank Reconciliation.
//
// Cambio v16 → v18 en el target del patch:
//   * v16: el widget `bank_rec_form_list` se registraba en la categoría
//     `view_widgets` del registry y exponía `bankRecListViewProps` como
//     getter. Lo parcheábamos con `Object.defineProperty`.
//   * v18: el widget jQuery fue reescrito como `BankRecKanbanController`
//     (Owl 2). La prop equivalente vive ahora en el método
//     `notebookAmlsListViewProps()` (kanban.js:774-798), que upstream
//     hardcodea a `allowSelectors: false` (línea 793). Patcheamos ese
//     método para devolver `true`.

import { patch } from "@web/core/utils/patch";
import { BankRecKanbanController } from "@account_accountant/components/bank_reconciliation/kanban";

patch(BankRecKanbanController.prototype, {
    notebookAmlsListViewProps() {
        const props = super.notebookAmlsListViewProps();
        return { ...props, allowSelectors: true };
    },
});
