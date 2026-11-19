# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of mail: compute `mail.activity.phone` left empty by pre-migration."""

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    activities = env["mail.activity"].with_context(active_test=False).search([])
    activities = activities.filtered(lambda a: a.res_model in env)
    env.add_to_compute(activities._fields["phone"], activities)
    activities.flush_recordset(["phone"])
