# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of mail.

`mail.activity.phone` (new, stored compute) reads the activity's document. Computed at column
creation, it fails for documents whose module is not loaded yet (KeyError: 'crm.lead').
Create the columns empty here; end-migration computes them once every model is loaded.
"""

from openupgradelib import openupgrade


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    for table in ("mail_activity", "mail_activity_schedule"):
        if openupgrade.table_exists(cr, table) and not openupgrade.column_exists(cr, table, "phone"):
            openupgrade.logged_query(cr, f"ALTER TABLE {table} ADD COLUMN phone varchar")
