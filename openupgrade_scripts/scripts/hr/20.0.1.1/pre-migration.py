# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of hr: hr.contract.type is renamed hr.employee.type
(OpenUpgrade apriori), and contract_type_id becomes employee_type_id."""

from openupgradelib import openupgrade


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    if not openupgrade.table_exists(cr, "hr_contract_type"):
        return
    openupgrade.rename_models(cr, [("hr.contract.type", "hr.employee.type")])
    openupgrade.rename_tables(cr, [("hr_contract_type", "hr_employee_type")])
    for table in ("hr_version", "hr_job"):
        if openupgrade.column_exists(cr, table, "contract_type_id"):
            openupgrade.rename_columns(cr, {table: [("contract_type_id", "employee_type_id")]})
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_model_fields SET name = 'employee_type_id', relation = 'hr.employee.type'
         WHERE name = 'contract_type_id' AND model IN ('hr.version', 'hr.job', 'hr.employee')
        """,
    )
