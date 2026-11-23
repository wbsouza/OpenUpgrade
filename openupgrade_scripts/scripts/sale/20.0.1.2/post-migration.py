# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 post-migration of sale.

``sale.cron`` is noupdate data an earlier upgrade left behind: sale ships it no more
and it runs the same code as ``sale.send_pending_emails_cron``
(``sale.order._cron_send_pending_emails()``), so the pending emails job could run
twice. The stale cron is deleted (logged); if it was the active one, the shipped cron
takes its active state.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

STALE_CRONS = {"sale.cron": "sale.send_pending_emails_cron"}


def _delete_duplicate_crons(env):
    for stale_xmlid, kept_xmlid in STALE_CRONS.items():
        stale = env.ref(stale_xmlid, raise_if_not_found=False)
        kept = env.ref(kept_xmlid, raise_if_not_found=False)
        if not (stale and kept) or (stale.model_id, (stale.code or "").strip()) != (
            kept.model_id,
            (kept.code or "").strip(),
        ):
            continue
        if stale.active and not kept.active:
            kept.active = True
        _logger.info(
            "UPGRADE20 stale cron %s (id %s, same code as %s id %s) deleted",
            stale_xmlid,
            stale.id,
            kept_xmlid,
            kept.id,
        )
        openupgrade.delete_records_safely_by_xml_id(
            env, [stale_xmlid, f"{stale_xmlid}_ir_actions_server"]
        )


@openupgrade.migrate()
def migrate(env, version):
    _delete_duplicate_crons(env)
