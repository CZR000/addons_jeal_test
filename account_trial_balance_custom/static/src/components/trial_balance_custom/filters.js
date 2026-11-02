/** @odoo-module */

import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

export class TrialBalanceCustomFilters extends AccountReportFilters {
    static template = "account_trial_balance_custom.TrialBalanceCustomFilters";
}

AccountReport.registerCustomComponent(TrialBalanceCustomFilters);
