# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of payment: provider `state` becomes `active` and `is_live`.

19.0 `state` was disabled / test / enabled. 20.0 drops it for `active` (default True) and
`is_live` (default False): without this mapping every disabled provider comes back active and
every enabled one in test mode, so a production database would take test payments.
"""

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    if not openupgrade.column_exists(cr, "payment_provider", "state"):
        return
    for column in ("active", "is_live"):
        if not openupgrade.column_exists(cr, "payment_provider", column):
            openupgrade.logged_query(cr, f"ALTER TABLE payment_provider ADD COLUMN {column} boolean")
    openupgrade.logged_query(
        cr,
        """UPDATE payment_provider
              SET active = state IS DISTINCT FROM 'disabled', is_live = state = 'enabled'""",
    )
