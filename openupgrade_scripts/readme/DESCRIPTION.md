This module is a containers of migration script to migrate from 19.0 to
20.0 version.

Modules covered by this branch:

| Module | What the scripts do |
|---|---|
| base | merged and renamed modules; drop views of merged modules and their website copies; deactivate views 20.0 no longer ships (XML ids in single or double quotes); release `ir.model.access` / `ir.rule` xmlids and xmlids whose model changed; detach templates that became standalone; `res.bank` → `res.partner.bank`, `acc_number` → `account_number`; `state_in_or` → `state_in_od`; `website.default_website` → `base.default_website` (else base data creates a second, empty website); install the new auto-install modules (`base_report_wkhtmltox`, without which no PDF prints); `res.device.log.user_agent`; custom ACLs and rules → `ir.access`; re-validate deferred views; `t-esc` / `t-raw` → `t-out` in stored QWeb views (noupdate templates, website copies); bank account country; Apps entries of modules whose code is gone removed (a module still owning business data stops the upgrade instead) |
| mail | `mail.activity.phone` computed after every model is loaded; web push (VAPID) key pair replaced and the browsers subscribed with the old keys removed; noupdate core mail templates still as their 19.0 file shipped them (fingerprint of their text fields) reloaded from their 20.0 file in every installed language, the others (customised or older) only get the calls 20.0 removed replaced (`ir.config_parameter.get_param`, `hr.applicant.user_id`, `sale.order.line.product_uom`, `calendar.event._get_attendee_emails`); the obsolete `base_install_request` template removed |
| account | stock valuation report moved from `stock_account`; payments in the dropped `in_process` state → `paid`, then core's compute moves the matched ones to `reconciled` |
| hr | `hr.contract.type` → `hr.employee.type`; `employee_type` selection → `employee_type_id` |
| crm_iap_mine | industries matched by name; the ones 20.0 dropped are removed and logged |
| sale | `product.template.sale_delay` integer → company-dependent jsonb |
| payment | provider `state` → `active` / `is_live` (disabled providers stay inactive, enabled ones stay live); methods are per provider: tokens and transactions repointed to the provider's own method, unused catalog rows removed, each provider's methods active as the 19.0 catalog method of the same code was for it |
| payment_custom | custom providers (Wire Transfer, Cash on Delivery) moved from the dropped `payment_custom.redirect_form` to `payment.generic_redirect_form` |
| resource | zero-hour lunch attendances removed |
| stock | `product.template.tracking` `'none'` → NULL (left as is, every product form crashed in `_compute_store_by`); picking type product label formats renamed (`2x7xprice` → `barcode_2x7_price`, ...); the `noupdate` package sequence keeps its 19.0 code `stock.quant.package` → `stock.package` (left as is, a package created without a typed name failed: no sequence numbered it) |
| website | obsolete generated "new page" templates removed |
| l10n_ca | companies on the `ca_2023` chart moved to the 20.0 Canadian chart of accounts (see Known issues) |
