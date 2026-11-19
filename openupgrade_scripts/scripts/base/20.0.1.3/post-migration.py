# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 post-migration of base: res.device.log.user_agent (required, new) replaces
the 19.0 `platform` / `browser` columns. Fill it from them so the NOT NULL constraint holds."""

from openupgradelib import openupgrade


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    if not openupgrade.column_exists(cr, "res_device_log", "browser"):
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_device_log
           SET user_agent = COALESCE(NULLIF(concat_ws(' / ', browser, platform), ''), 'Unknown')
         WHERE user_agent IS NULL
        """,
    )
