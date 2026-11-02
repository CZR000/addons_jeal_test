import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";
import { patch } from "@web/core/utils/patch";

patch(AccountReportFilters.prototype, {
    onGroupingChange(optionKey) {
        const currentValue = this.controller.options[optionKey] || false;
        this.filterClicked({ optionKey: optionKey, optionValue: !currentValue, reload: true });
    },
    getMultiRecordSelectorProps(resModel, optionKey) {
        const customFilters = [
            'filter_warehouse_ids',
            'filter_location_ids',
            'filter_category_ids',
            'filter_product_ids',
        ];
        if (customFilters.includes(optionKey)) {
            return {
                resModel: resModel,
                resIds: this.controller.options[optionKey] || [],
                update: (resIds) => {
                    this.filterClicked({ optionKey: optionKey, optionValue: resIds, reload: true });
                },
            };
        }
        return super.getMultiRecordSelectorProps(...arguments);
    },
});
