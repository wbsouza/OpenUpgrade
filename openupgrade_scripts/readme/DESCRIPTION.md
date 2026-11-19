This module is a containers of migration script to migrate from 19.0 to
20.0 version.

Modules covered by this branch:

| Module | What the scripts do |
|---|---|
| base | merged and renamed modules; drop views of merged modules and their website copies; deactivate views 20.0 no longer ships; release `ir.model.access` / `ir.rule` xmlids and xmlids whose model changed; detach templates that became standalone; `res.bank` → `res.partner.bank`, `acc_number` → `account_number`; `state_in_or` → `state_in_od`; install the new auto-install modules (`base_report_wkhtmltox`, without which no PDF prints); `res.device.log.user_agent`; custom ACLs and rules → `ir.access`; re-validate deferred views; bank account country |
| mail | `mail.activity.phone` computed after every model is loaded |
| account | stock valuation report moved from `stock_account` |
| hr | `hr.contract.type` → `hr.employee.type`; `employee_type` selection → `employee_type_id` |
| crm_iap_mine | industries matched by name; the ones 20.0 dropped are removed and logged |
| sale | `product.template.sale_delay` integer → company-dependent jsonb |
| payment | methods are per provider: tokens and transactions repointed to the provider's own method, unused catalog rows removed |
| payment_custom | custom providers (Wire Transfer, Cash on Delivery) moved from the dropped `payment_custom.redirect_form` to `payment.generic_redirect_form` |
| resource | zero-hour lunch attendances removed |
| website | obsolete generated "new page" templates removed |
| l10n_ca | companies on the `ca_2023` chart moved to the 20.0 Canadian chart of accounts (see Known issues) |
