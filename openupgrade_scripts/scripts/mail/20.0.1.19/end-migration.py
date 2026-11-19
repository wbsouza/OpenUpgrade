# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of mail.

- Compute `mail.activity.phone`, left empty by pre-migration.
- Replace the web push (VAPID) key pair: the 19.0 keys and the browsers subscribed with them are
  removed and a new pair is generated, so nothing is tied to the old keys. A browser that still
  holds an old subscription is refused once, then subscribes again with the new key.
  Idempotent: each run leaves exactly one fresh pair and no stale subscription. Neutralize later
  drops the pair on test copies; Odoo generates another on the first visit.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

VAPID_KEYS = ("mail.web_push_vapid_private_key", "mail.web_push_vapid_public_key")


@openupgrade.migrate()
def migrate(env, version):
    activities = env["mail.activity"].with_context(active_test=False).search([])
    activities = activities.filtered(lambda a: a.res_model in env)
    env.add_to_compute(activities._fields["phone"], activities)
    activities.flush_recordset(["phone"])

    devices = env["mail.push.device"].sudo().search([])
    keys = env["ir.config_parameter"].sudo().search([("key", "in", VAPID_KEYS)])
    devices.unlink()
    keys.unlink()
    env["mail.push.device"].get_web_push_vapid_public_key()  # generates the new pair
    _logger.info("web push reset: %d subscribed browsers and %d VAPID keys replaced", len(devices), len(keys))
