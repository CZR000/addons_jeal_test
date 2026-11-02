/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { BankRecAmlsRenderer } from "@account_accountant/components/bank_reconciliation/amls_list_view";
import { ListController } from "@web/views/list/list_controller";
import { onPatched } from "@odoo/owl";

patch(BankRecAmlsRenderer.prototype, {
    setup() {
        super.setup();
        onPatched(() => this._brcSyncCheckboxesToRecon());
    },

    async toggleRecordSelection(record) {
        const reconIds = this._brcGetReconIds();
        if (reconIds.has(record.resId)) {
            await this.env.config.actionRemoveNewAml(record.resId);
        } else {
            await this.env.config.actionAddNewAml(record.resId);
        }
    },

    _brcGetReconIds() {
        const ids = this.globalState?.bankRecRecordData?.selected_aml_ids?.currentIds || [];
        return new Set(ids);
    },

    _brcSyncCheckboxesToRecon() {
        const reconIds = this._brcGetReconIds();
        for (const record of (this.props?.list?.records || [])) {
            const shouldBeSelected = reconIds.has(record.resId);
            if (record.selected !== shouldBeSelected) {
                record.toggleSelection(shouldBeSelected);
            }
        }
    },
});

patch(ListController.prototype, {
    async onUnselectAll() {
        if (!this.env.config?.actionRemoveNewAml) {
            return super.onUnselectAll(...arguments);
        }
        const amlIds = this.model.root.selection.map((r) => r.resId);
        for (const amlId of amlIds) {
            await this.env.config.actionRemoveNewAml(amlId);
        }
    },
});