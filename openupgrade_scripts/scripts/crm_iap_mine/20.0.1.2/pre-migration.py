# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of crm_iap_mine: the industry list was rebuilt (SIC groups, new
xmlids). An existing industry whose name matches a 20.0 row takes the new xmlid, so the
unique name constraint holds and leads keep their industry. Industries with no 20.0
equivalent are deleted here (Odoo's cleanup would delete them anyway, but only after the
NOT NULL constraints on sic_group/division_id are skipped); each one is logged."""

import csv
import os

from odoo.modules.module import get_module_path
from openupgradelib import openupgrade


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    path = os.path.join(get_module_path("crm_iap_mine"), "data", "crm.iap.lead.industry.csv")
    with open(path, newline="") as data:
        new_ids = {row["name"]: row["id"] for row in csv.DictReader(data)}
    cr.execute("""SELECT d.id, d.name, i.name->>'en_US' FROM ir_model_data d
             JOIN crm_iap_lead_industry i ON i.id = d.res_id
            WHERE d.model = 'crm.iap.lead.industry' AND d.module = 'crm_iap_mine'""")
    for data_id, old_name, label in cr.fetchall():
        new_name = new_ids.get(label)
        if new_name and new_name != old_name:
            cr.execute("DELETE FROM ir_model_data WHERE module = 'crm_iap_mine' AND name = %s", [new_name])
            openupgrade.logged_query(cr, "UPDATE ir_model_data SET name = %s WHERE id = %s", [new_name, data_id])
    matched = set(new_ids)
    cr.execute("""SELECT i.id, i.name->>'en_US',
                  (SELECT count(*) FROM crm_iap_lead_industry_crm_iap_lead_mining_request_rel r
                    WHERE r.crm_iap_lead_industry_id = i.id)
             FROM crm_iap_lead_industry i""")
    obsolete = [(i, label, uses) for i, label, uses in cr.fetchall() if label not in matched]
    for industry_id, label, uses in obsolete:
        openupgrade.logger.warning(
            "crm_iap_mine: industry %r has no 20.0 equivalent, removed (%s mining requests)", label, uses
        )
    if obsolete:
        ids = [o[0] for o in obsolete]
        cr.execute("DELETE FROM ir_model_data WHERE model = 'crm.iap.lead.industry' AND res_id = ANY(%s)", [ids])
        openupgrade.logged_query(cr, "DELETE FROM crm_iap_lead_industry WHERE id = ANY(%s)", [ids])
