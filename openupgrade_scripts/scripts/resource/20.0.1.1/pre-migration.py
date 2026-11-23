# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of resource.

- 19.0 stored lunch breaks as zero-hour attendances (day_period 'lunch'). 20.0 has no lunch
  period and requires 0 < duration_hours <= 24. A lunch row never counted as work time, so
  removing it keeps every calendar's working hours.
- ``res.company.tz``: 19.0 related to the company partner's timezone, 20.0 a stored computed field
  that also replaces the dropped ``resource.calendar.tz`` (working hours are read in the company's
  timezone). Left to its compute it takes the superuser's timezone, or the country's when the
  country has only one: UTC for a company of a multi-timezone country, which moved working hours,
  leaves and attendances by hours. It keeps the 19.0 company timezone, else the timezone of the
  company's default working hours (UTC when neither is set, as 19.0 then read it).
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    openupgrade.logged_query(
        cr, "DELETE FROM resource_calendar_attendance WHERE day_period = 'lunch' AND hour_to - hour_from <= 1"
    )
    _company_timezone(cr)


def _company_timezone(cr):
    if openupgrade.column_exists(cr, "res_company", "tz") or not openupgrade.column_exists(
        cr, "resource_calendar", "tz"
    ):
        return
    cr.execute("ALTER TABLE res_company ADD COLUMN tz varchar")
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_company c
           SET tz = coalesce(p.tz, cal.tz, 'UTC')
          FROM res_company c2
          LEFT JOIN res_partner p ON p.id = c2.partner_id
          LEFT JOIN resource_calendar cal ON cal.id = c2.resource_calendar_id
         WHERE c2.id = c.id
        """,
    )
    cr.execute(
        """
        SELECT cal.id, cal.tz, c.tz FROM resource_calendar cal JOIN res_company c ON c.id = cal.company_id
         WHERE cal.active AND cal.tz IS DISTINCT FROM c.tz
        """
    )
    for calendar_id, calendar_tz, company_tz in cr.fetchall():
        _logger.warning(
            "UPGRADE20 working hours %s were in %s; 20.0 reads them in their company's timezone %s",
            calendar_id,
            calendar_tz,
            company_tz,
        )
