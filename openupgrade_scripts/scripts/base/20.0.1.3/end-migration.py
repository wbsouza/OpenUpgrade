# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of base: convert hand-made ACLs and record rules to ir.access.

Module-owned rows are recreated from each module's security files during -u all (see
pre-migration). Rows created in the UI (no xmlid, or an __export__/__custom__ one) have no
file behind them, so they are rebuilt here from the 19.0 tables ir_model_access / ir_rule.
"""

import logging
from pathlib import Path

from odoo.modules.module import get_module_path
from odoo.tools.misc import file_path
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
    remove_vanished_modules(env)
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


# The repository root: openupgrade_framework / openupgrade_scripts are on the addons path only
# while upgrading, never in normal operation, so their Apps entries would be left behind.
UPGRADE_ADDONS = Path(__file__).resolve().parents[4]


def _icon_exists(icon):
    try:
        return bool(icon) and bool(file_path(icon.lstrip("/")))
    except (FileNotFoundError, ValueError):
        return False


def _vanished(module):
    path = get_module_path(module.name, display_warning=False)
    if path and Path(path).resolve().parent == UPGRADE_ADDONS:
        return True
    return not path and (not module.to_buy or not _icon_exists(module.icon))


def remove_vanished_modules(env):
    """Apps entries of modules whose code is gone: 19.0 addons left out of the 20.0 addons path,
    and Enterprise "buy" entries (no code by design) 20.0 dropped, recognised by their missing
    icon. Updating the module list never deletes a row, so the Apps screen kept them and asked for
    their icon (404). A module installed on 19.0 is not loaded either: Odoo marks it uninstalled
    only after the end-migrations, so it is matched here too; its leftover data stays. The
    upgrade's own tooling addons are removed too. Idempotent: a second run finds nothing."""
    vanished = env["ir.module.module"].search([]).filtered(_vanished)
    _uninstall_vanished(vanished.filtered(lambda m: m.state in INSTALLED_STATES))
    _logger.info("removed %s vanished modules: %s", len(vanished), ", ".join(sorted(vanished.mapped("name"))))
    vanished.write({"state": "uninstalled"})  # unlink refuses an installed module
    vanished.unlink()


INSTALLED_STATES = ("installed", "to upgrade", "to remove")


def _data_at_risk(env, module):
    """What uninstalling `module` would destroy: stored models and stored columns of models that
    are not transient, owned by this module alone. Views, actions, menus, wizards and settings
    fields hold no business data."""
    data = env["ir.model.data"].search([("module", "=", module.name), ("model", "in", ("ir.model", "ir.model.fields"))])
    shared = env["ir.model.data"].search(
        [
            ("module", "!=", module.name),
            ("model", "in", ("ir.model", "ir.model.fields")),
            ("res_id", "in", data.mapped("res_id")),
        ]
    )
    owned_alone = data.filtered(lambda d: (d.model, d.res_id) not in {(s.model, s.res_id) for s in shared})
    risk = []
    for record in owned_alone:
        if record.model == "ir.model":
            model = env["ir.model"].browse(record.res_id).exists()
            if model and not model.transient and _table_has_rows(env, model.model.replace(".", "_")):
                risk.append(f"model {model.model}")
        else:
            field = env["ir.model.fields"].browse(record.res_id).exists()
            if field and field.store and not env["ir.model"]._get(field.model).transient:
                risk.append(f"field {field.model}.{field.name}")
    return risk


def _table_has_rows(env, table):
    if not openupgrade.table_exists(env.cr, table):
        return False
    env.cr.execute(f'SELECT 1 FROM "{table}" LIMIT 1')  # table name from ir.model, not user input
    return bool(env.cr.rowcount)


def _uninstall_vanished(modules):
    """A module installed on 19.0 whose code is gone left its views, actions, menus and fields
    behind; a leftover view breaks the screen it extends (Settings: "field is undefined"). Remove
    them with Odoo's own uninstall when nothing but configuration would go. When the module owns
    business data, stop: logged as ERROR, so the upgrade run fails and a person decides."""
    for module in modules:
        risk = _data_at_risk(module.env, module)
        if risk:
            _logger.error("vanished module %s still owns data, not uninstalled: %s", module.name, ", ".join(risk[:10]))
            continue
        module._remove_copied_views()
        _remove_views_extending(module)
        module.module_uninstall()
        _logger.info("uninstalled vanished module %s (configuration only)", module.name)


def _remove_views_extending(module):
    """Views of other modules that extend this module's views cannot work once it is gone, and
    the foreign key on inherit_id stops the uninstall from deleting the parents. A retired 19.0
    module's view is one (website_seo extended website_webkul_addons' settings): Odoo deletes it
    only after the end-migrations. Delete them first, deepest first."""
    View = module.env["ir.ui.view"].with_context(active_test=False, force_delete=True)
    owned = module.env["ir.model.data"].search([("module", "=", module.name), ("model", "=", "ir.ui.view")])
    parents = View.browse(owned.mapped("res_id")).exists()
    children = View.search([("inherit_id", "in", parents.ids)]) - parents
    if children:
        _logger.info("removing views %s: they extend views of vanished module %s", children.ids, module.name)
        _unlink_deepest_first(View, children)


def _unlink_deepest_first(View, views):
    descendants = View.search([("inherit_id", "in", views.ids)]) - views
    if descendants:
        _unlink_deepest_first(View, descendants)
    views.unlink()
