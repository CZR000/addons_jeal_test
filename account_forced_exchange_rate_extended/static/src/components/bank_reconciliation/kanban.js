import { registry } from "@web/core/registry";
import { FloatField } from "@web/views/fields/float/float_field";
import { SelectionField } from "@web/views/fields/selection/selection_field";

/**
 * Espejo de: account_accountant/static/src/components/bank_reconciliation/kanban.js
 *
 * Hace que <FloatField/> y <SelectionField/> se resuelvan en el panel
 * "Operaciones manuales", que renderiza el controlador de la conciliación.
 *
 * No basta parchear `BankRecKanbanController`: sus subclases copian el mapa
 * `components` al cargarse, antes que este archivo, y `account_bank_statement_import`
 * además re-registra la vista con `force: true`. Por eso se parchea el
 * controlador realmente registrado y se escucha `UPDATE` para cubrir a
 * cualquier módulo que registre su variante más tarde.
 */

const VIEW_KEY = "bank_rec_widget_kanban";
const viewsRegistry = registry.category("views");

const EXTRA_COMPONENTS = { FloatField, SelectionField };

/**
 * Añade los componentes de campo al controlador de una vista.
 *
 * @param {Object|null} view Descriptor de vista del registro `views`.
 */
function registerFieldComponents(view) {
    const Controller = view && view.Controller;
    if (!Controller) {
        return;
    }
    Controller.components = { ...Controller.components, ...EXTRA_COMPONENTS };
}

registerFieldComponents(viewsRegistry.get(VIEW_KEY, null));

viewsRegistry.addEventListener("UPDATE", ({ detail }) => {
    if (detail.key === VIEW_KEY && detail.operation === "add") {
        registerFieldComponents(detail.value);
    }
});
