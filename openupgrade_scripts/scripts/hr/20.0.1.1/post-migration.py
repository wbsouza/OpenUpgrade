# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 post-migration of hr: the 19.0 `employee_type` selection is gone; carry its
meaning into employee_type_id where no contract type was set."""

from openupgradelib import openupgrade

SELECTION_TO_TYPE = {
    "employee": "hr.contract_type_employee",
    "student": "hr.contract_type_student",
    "trainee": "hr.contract_type_intern",
}


@openupgrade.migrate()
def migrate(env, version):
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
