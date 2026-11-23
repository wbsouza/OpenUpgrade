# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 post-migration of hr: the 19.0 `employee_type` selection is gone; carry its
meaning into employee_type_id where no contract type was set.

Scheduled actions hr no longer ships and whose method is gone are deleted (logged):
noupdate data an earlier upgrade left behind, failing on every run.
``ir_cron_data_check_work_permit_validity`` calls
``hr.employee._cron_check_work_permit_validity``, long replaced by
``ir_cron_data_employee_notify_expiring_contract_work_permit``.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

STALE_CRONS = {
    "hr.ir_cron_data_check_work_permit_validity": "_cron_check_work_permit_validity"
}

SELECTION_TO_TYPE = {
    "employee": "hr.contract_type_employee",
    "student": "hr.contract_type_student",
    "trainee": "hr.contract_type_intern",
}


def _delete_stale_crons(env):
    for xmlid, method in STALE_CRONS.items():
        cron = env.ref(xmlid, raise_if_not_found=False)
        if not cron or hasattr(env[cron.model_id.model], method):
            continue
        _logger.info(
            "UPGRADE20 stale cron %s (id %s, %s.%s is gone) deleted",
            xmlid,
            cron.id,
            cron.model_id.model,
            method,
        )
        openupgrade.delete_records_safely_by_xml_id(
            env, [xmlid, f"{xmlid}_ir_actions_server"]
        )


@openupgrade.migrate()
def migrate(env, version):
    _delete_stale_crons(env)
    if not openupgrade.column_exists(env.cr, "hr_version", "employee_type"):
        return
    for selection, xmlid in SELECTION_TO_TYPE.items():
        employee_type = env.ref(xmlid, raise_if_not_found=False)
        if employee_type:
            openupgrade.logged_query(
                env.cr,
                """UPDATE hr_version SET employee_type_id = %s
                    WHERE employee_type_id IS NULL AND employee_type = %s""",
                [employee_type.id, selection],
            )
