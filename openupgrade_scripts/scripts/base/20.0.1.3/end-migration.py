# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of base: convert hand-made ACLs and record rules to ir.access.

Module-owned rows are recreated from each module's security files during -u all (see
pre-migration). Rows created in the UI (no xmlid, or an __export__/__custom__ one) have no
file behind them, so they are rebuilt here from the 19.0 tables ir_model_access / ir_rule.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

OPS = [("perm_create", "c"), ("perm_read", "r"), ("perm_write", "u"), ("perm_unlink", "d")]


def _operation(row):
    return "".join(letter for column, letter in OPS if row[column])


def _hand_made(cr, table, model):
    cr.execute(
        f"""
        SELECT t.*, m.model AS model_name
          FROM {table} t
          JOIN ir_model m ON m.id = t.model_id
          JOIN openupgrade_legacy_20_0_custom_access c ON c.model = %s AND c.res_id = t.id
        """,
        [model],
    )
    return cr.dictfetchall()


def _create(env, vals, source):
    if vals["model_name"] not in env:
        _logger.warning("ir.access: skip %s, model %s is not loaded", source, vals["model_name"])
        return
    if not vals["operation"]:
        return
    access = env["ir.access"].create(
        {
            "name": vals["name"],
            "active": vals["active"],
            "model_id": env["ir.model"]._get_id(vals["model_name"]),
            "group_id": vals["group_id"],
            "operation": vals["operation"],
            "domain": vals["domain"],
        }
    )
    _logger.info("ir.access %s created from %s", access.id, source)


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    revalidate_deferred_views(env)
    # res.partner.bank.country_id (precomputed) was added by pre-migration from res.bank, so
    # Odoo did not compute it for accounts whose bank had no country
    banks = env["res.partner.bank"].with_context(active_test=False).search([("country_id", "=", False)])
    banks._compute_country_id()
    banks.flush_recordset(["country_id"])
    if not openupgrade.table_exists(cr, "openupgrade_legacy_20_0_custom_access"):
        return
    for row in _hand_made(cr, "ir_model_access", "ir.model.access"):
        vals = dict(row, operation=_operation(row), domain=False)
        _create(env, vals, f"ir.model.access {row['id']}")
    for row in _hand_made(cr, "ir_rule", "ir.rule"):
        cr.execute("SELECT group_id FROM rule_group_rel WHERE rule_group_id = %s", [row["id"]])
        group_ids = [gid for (gid,) in cr.fetchall()] or [False]
        domain = row["domain_force"] if row["domain_force"] not in (None, "", "[]", "[(1,'=',1)]") else False
        for group_id in group_ids:
            if not group_id and not domain:
                continue  # a global rule that allows everything restricts nothing
            vals = dict(row, group_id=group_id, operation=_operation(row), domain=domain)
            _create(env, vals, f"ir.rule {row['id']}")


def revalidate_deferred_views(env):
    """Views whose validation openupgrade_framework deferred: check them again now that
    every module is loaded. Still invalid = a real problem, logged as ERROR."""
    if not openupgrade.table_exists(env.cr, "openupgrade_legacy_20_0_deferred_view"):
        return
    env.cr.execute("SELECT view_id FROM openupgrade_legacy_20_0_deferred_view")
    views = env["ir.ui.view"].browse([vid for (vid,) in env.cr.fetchall()]).exists().filtered("active")
    # obsolete views (xmlid not loaded by this upgrade, not noupdate) are deleted right after
    # the end-migrations by ir.model.data._process_end: do not judge them
    loaded = env.registry.loaded_xmlids
    data = env["ir.model.data"].search([("model", "=", "ir.ui.view"), ("res_id", "in", views.ids)])
    doomed = {d.res_id for d in data if not d.noupdate and d.complete_name not in loaded}
    views = views.filtered(lambda v: v.id not in doomed)
    check = getattr(type(views), "_openupgrade_check_xml", type(views)._check_xml)
    for view in views:
        try:
            with env.cr.savepoint():
                check(view)
        except Exception as error:  # noqa: BLE001
            _logger.error("UPGRADE20 view still invalid %s (%s): %s", view.id, view.xml_id, str(error)[:500])
    _logger.info("UPGRADE20 re-validated %s deferred views", len(views))
