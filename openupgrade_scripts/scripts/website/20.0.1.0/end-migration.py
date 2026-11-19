# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of website: drop obsolete generated "new page" templates.

website generates `website.new_page_template_sections_<group>_<name>` and their snippet
templates from code, for the page templates 20.0 still lists. The 19.0-only section templates
stay (noupdate) while the snippet templates they t-call are removed by ir.model.data
_process_end right after the end-migrations, so choosing them in the New Page dialog fails.
They are generated data, not customizations (website_id is NULL).
"""

import re

from openupgradelib import openupgrade

T_CALL = re.compile(r't-call="([a-z0-9_]+\.[a-zA-Z0-9_.]+)"')


def _view_kept(env, view, loaded):
    """The cleanup deletes a view whose xmlid was not loaded (and is not noupdate), and
    unlinking a view also deletes the views inheriting from it: check the whole chain."""
    while view:
        data = env["ir.model.data"].search([("model", "=", "ir.ui.view"), ("res_id", "=", view.id)])
        if data and not any(d.noupdate or d.complete_name in loaded for d in data):
            return False
        view = view.inherit_id
    return True


def _survives(env, xmlid, loaded):
    """True when the template exists and is kept by the end-of-upgrade cleanup."""
    views = env["ir.ui.view"].with_context(active_test=False).search([("key", "=", xmlid), ("website_id", "=", False)])
    return any(_view_kept(env, view, loaded) for view in views)


@openupgrade.migrate()
def migrate(env, version):
    loaded = env.registry.loaded_xmlids
    sections = (
        env["ir.ui.view"]
        .with_context(active_test=False)
        .search([("key", "=like", "website.new_page_template_sections_%"), ("website_id", "=", False)])
    )
    dangling = sections.filtered(
        lambda view: any(not _survives(env, target, loaded) for target in T_CALL.findall(view.arch_db or ""))
    )
    if not dangling:
        return
    cr = env.cr
    cr.execute(
        """WITH RECURSIVE tree(id, depth) AS (
               SELECT unnest(%s::int[]), 0
               UNION SELECT v.id, t.depth + 1 FROM ir_ui_view v JOIN tree t ON v.inherit_id = t.id)
           SELECT id, max(depth) FROM tree GROUP BY id ORDER BY 2 DESC""",
        [dangling.ids],
    )
    by_depth = {}
    for view_id, depth in cr.fetchall():
        by_depth.setdefault(depth, []).append(view_id)
    for depth in sorted(by_depth, reverse=True):
        level = by_depth[depth]
        cr.execute("DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id = ANY(%s)", [level])
        openupgrade.logged_query(cr, "DELETE FROM ir_ui_view WHERE id = ANY(%s)", [level])
    env.invalidate_all()
