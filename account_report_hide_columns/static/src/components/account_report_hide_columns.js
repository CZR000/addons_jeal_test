/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

patch(AccountReportFilters.prototype, {
    get hasUIFilter() {
        return super.hasUIFilter || (
            this.controller.filters.show_hide_0_columns
            && this.controller.filters.show_hide_0_columns !== "never"
        );
    },
});
