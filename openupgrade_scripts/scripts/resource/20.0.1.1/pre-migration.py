# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of resource: 19.0 stored lunch breaks as zero-hour attendances
(day_period 'lunch'). 20.0 has no lunch period and requires 0 < duration_hours <= 24. A lunch
row never counted as work time, so removing it keeps every calendar's working hours."""

from openupgradelib import openupgrade


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    openupgrade.logged_query(
        cr, "DELETE FROM resource_calendar_attendance WHERE day_period = 'lunch' AND hour_to - hour_from <= 1"
    )
