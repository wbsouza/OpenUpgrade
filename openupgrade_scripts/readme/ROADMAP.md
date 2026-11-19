Known issues and limitations:

- **l10n_ca chart of accounts.** The 19.0 and 20.0 `ca_2023` charts share
  no accounts (19.0: numbered accounts and `account.group`; 20.0: named
  accounts without codes). Accounts with postings or used as defaults are
  adopted (same record, so lines, partners, taxes and journals stay linked;
  they keep their old code); account 411000 and the generated cash
  difference accounts are merged into their 20.0 counterpart; the other
  20.0 accounts are created; unused 19.0 accounts are archived. Only
  accounts are loaded: taxes, fiscal positions and journals are not
  changed, so purchase taxes still point to archived 19.0 accounts and must
  be mapped manually. The migration fails if any account balance changes.
  The `account_group` table is kept.
- **crm_iap_mine.** Industries with no 20.0 equivalent are removed.
- **Views.** `noupdate` views that 20.0 no longer ships are deactivated,
  not deleted.
