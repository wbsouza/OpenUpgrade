Run the 20.0 server on a copy of the 19.0 database with:

``` shell
odoo-bin -d <db> -u all --stop-after-init \
  --upgrade-path=/PATH_TO_openupgrade_scripts_MODULE/scripts/ \
  --load=base,web,openupgrade_framework
```

The script folder is `20.0.` + the module's manifest version (`20.0.1.0` when
the manifest has none).

`openupgrade_framework` is loaded server-wide, never installed. A view that
fails validation while its module loads is logged and queued; the `base`
end-migration re-validates the queue and logs an error for each view still
invalid.

Tables left in the upgraded database for review:

- `openupgrade_legacy_20_0_deactivated_view`
- `openupgrade_legacy_20_0_deferred_view`
- `openupgrade_legacy_20_0_custom_access`

Recommended checks:

- Rehearse on a copy of the database and its filestore, backed up together.
- Compare record counts and accounting totals (trial balance, aged
  receivables and payables, open invoices) before and after.
- Render every report and review the deactivated views.
- Coverage is partial: a database can hit a rename these scripts do not
  handle. Fix it with an additional migration script, not by editing core.
