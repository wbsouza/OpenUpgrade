# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of base.

Module renames/merges come from apriori.py.
"""

import os
import re

from openupgradelib import openupgrade

from odoo.modules.module import get_module_path

RENAMED_MODULES = {
    "purchase_requisition_sale": "purchase_alternative_sale",
    "website_sale_autocomplete": "website_address_autocomplete",
}

MERGED_MODULES = {
    "account_add_gln": "account",
    "account_peppol_response": "account_peppol",
    "base_iban": "account",
    "base_vat": "base",
    "delivery_stock_picking_batch": "stock_delivery",
    "hr_holidays_homeworking": "hr_holidays",
    "hr_homeworking": "hr",
    "hr_homeworking_calendar": "hr_calendar",
    "hr_hourly_cost": "hr",
    "hr_org_chart": "hr",
    "hr_work_entry_holidays": "hr_holidays",
    "l10n_latam_base": "account",
    "stock_picking_batch": "stock",
    "website_sale_collect_wishlist": "website_sale_collect",
    "website_sale_comparison": "website_sale",
    "website_sale_comparison_wishlist": "website_sale",
    "website_sale_stock_wishlist": "website_sale_stock",
    "website_sale_wishlist": "website_sale",
}

# OpenUpgrade apriori renamed_models / merged_models: a record of the old model under an xmlid
# that 20.0 declares on the new model is the same record, migrated by the module's own script.
RENAMED_MODELS = {
    "hr.contract.type": "hr.employee.type",
    "website.base.unit": "product.base.unit",
    "stock_account.stock.valuation.report": "account.stock.valuation.report",
    "google.calendar.sync": "google.event.sync",
    "calendar.popover.delete.wizard": "calendar.event.archive.or.unlink.wizard",
    "purchase.requisition.alternative.warning": "purchase.alternative.warning",
    "purchase.requisition.create.alternative": "purchase.alternative.create",
    "ir.model.access": "ir.access",
    "ir.rule": "ir.access",
    "res.bank": "res.partner.bank",
    "stock.scrap": "stock.move",
    "hr.leave.type": "hr.work.entry.type",
    "crm.lead2opportunity.partner": "crm.lead2opportunity.partner.mass",
}

# New in 20.0 and auto_install: a fresh 20.0 database gets them, -u all on a 19.0 one does not.
# Without base_report_wkhtmltox no PDF can be printed at all ("Unable to find the pdf engine").
NEW_AUTO_INSTALL = {
    "base_report_wkhtmltox": [],
    "mysubscription": ["web"],
    "portal_discuss": ["mail", "portal"],
    "account_payment_custom": ["account_payment", "payment_custom"],
}

XMLID_RENAMES = [
    ("base.state_in_or", "base.state_in_od"),
]

PARTNER_BANK_FIELDS = [
    ("res.partner.bank", "res_partner_bank", "acc_number", "account_number"),
    ("res.partner.bank", "res_partner_bank", "sanitized_acc_number", "sanitized_account_number"),
    ("res.partner.bank", "res_partner_bank", "acc_holder_name", "holder_name"),
]


def _fold_res_bank_into_partner_bank(cr):
    """res.bank is merged into res.partner.bank: copy the bank's data onto each account."""
    if not openupgrade.column_exists(cr, "res_partner_bank", "bank_id"):
        return
    for column, sql_type in [
        ("bank_name", "varchar"),
        ("bank_bic", "varchar"),
        ("street", "varchar"),
        ("street2", "varchar"),
        ("zip", "varchar"),
        ("city", "varchar"),
        ("state_id", "integer"),
        ("country_id", "integer"),
    ]:
        if not openupgrade.column_exists(cr, "res_partner_bank", column):
            openupgrade.logged_query(cr, f"ALTER TABLE res_partner_bank ADD COLUMN {column} {sql_type}")
    openupgrade.logged_query(
        cr,
        """
        UPDATE res_partner_bank rpb
           SET bank_name = rb.name, bank_bic = rb.bic, street = rb.street, street2 = rb.street2,
               zip = rb.zip, city = rb.city, state_id = rb.state, country_id = rb.country
          FROM res_bank rb
         WHERE rpb.bank_id = rb.id
        """,
    )


def _drop_views_of_merged_modules(cr):
    """A merged module's 19.0 views become `base`/`account`/... views and stay active, but they
    reference fields that moved elsewhere in 20.0 (base_vat → perform_vies_validation). Delete
    them, descendants first (inherit_id is ON DELETE RESTRICT); the target module recreates the
    views 20.0 still has, and every inheriting module recreates its own children on -u all."""
    cr.execute(
        """
        WITH RECURSIVE tree(id, depth) AS (
            SELECT res_id, 0 FROM ir_model_data WHERE model = 'ir.ui.view' AND module = ANY(%s)
            UNION
            -- website-specific copies (no xmlid, same key) made by the website editor
            SELECT id, 0 FROM ir_ui_view WHERE website_id IS NOT NULL AND split_part(key, '.', 1) = ANY(%s)
            UNION
            SELECT v.id, t.depth + 1 FROM ir_ui_view v JOIN tree t ON v.inherit_id = t.id
        )
        SELECT id, max(depth) FROM tree GROUP BY id ORDER BY 2 DESC
        """,
        [list(MERGED_MODULES), list(MERGED_MODULES)],
    )
    by_depth = {}
    for view_id, depth in cr.fetchall():
        by_depth.setdefault(depth, []).append(view_id)
    for depth in sorted(by_depth, reverse=True):
        ids = by_depth[depth]
        openupgrade.logged_query(cr, "DELETE FROM ir_ui_view WHERE id = ANY(%s)", [ids])
        openupgrade.logged_query(cr, "DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id = ANY(%s)", [ids])


def _free_acl_xmlids(cr):
    """ir.model.access and ir.rule are merged into ir.access. Every module reloads its own
    security files on -u all and recreates its rows as ir.access under the same xmlids, so the
    old xmlids must not point at the old models any more. Rows without a module xmlid are
    converted by base end-migration from the old tables, which are left in place."""
    cr.execute("CREATE TABLE IF NOT EXISTS openupgrade_legacy_20_0_custom_access (model varchar, res_id integer)")
    for model, table in (("ir.model.access", "ir_model_access"), ("ir.rule", "ir_rule")):
        openupgrade.logged_query(
            cr,
            f"""
            INSERT INTO openupgrade_legacy_20_0_custom_access
            SELECT %s, t.id FROM {table} t
              LEFT JOIN ir_model_data d ON d.model = %s AND d.res_id = t.id
                   AND d.module NOT IN ('__export__', '__custom__', 'studio_customization')
             WHERE d.id IS NULL
            """,
            [model, model],
        )
    openupgrade.logged_query(
        cr,
        """
        DELETE FROM ir_model_data
         WHERE model IN ('ir.model.access', 'ir.rule')
           AND module NOT IN ('__export__', '__custom__', 'studio_customization')
        """,
    )


# XML attributes may be single-quoted (fleet: <record id='fleet_vehicle_view_form' ...>)
_XML_ID = re.compile(r"""\bid=(?:"([\w.\-]+)"|'([\w.\-]+)')""")
_RECORD = re.compile(r"<(record|template|menuitem)\b([^>]*)>", re.S)
_ATTR = re.compile(r"""\b(id|model)=(?:"([^"]+)"|'([^']+)')""")
_TAG_MODEL = {"template": "ir.ui.view", "menuitem": "ir.ui.menu"}
# old records of these models are deleted with their xmlid: keeping them duplicates a menu,
# a binding or a cron. Data records (partners, products, ...) only lose the xmlid.
_TECHNICAL = (
    "ir.actions.act_window",
    "ir.actions.server",
    "ir.actions.client",
    "ir.actions.report",
    "ir.actions.act_url",
    "ir.ui.menu",
    "ir.cron",
)


def _xml_sources(module):
    """Text of every data XML file of the module's 20.0 source (static/ and tests excluded);
    None when the module is not on the addons path."""
    path = get_module_path(module, display_warning=False)
    if not path:
        return None
    sources = []
    for dirpath, _dirs, files in os.walk(path):
        if f"{os.sep}static{os.sep}" in dirpath + os.sep or f"{os.sep}tests" in dirpath:
            continue
        for name in files:
            if name.endswith(".xml"):
                with open(os.path.join(dirpath, name), errors="ignore") as xml:
                    sources.append(xml.read())
    return sources


def _qualified(module, xmlid):
    return xmlid if "." in xmlid else f"{module}.{xmlid}"


def _xml_ids_of(module):
    sources = _xml_sources(module)
    if sources is None:
        return None
    return {_qualified(module, x) for source in sources for pair in _XML_ID.findall(source) for x in pair if x}


def _xml_tags_of(module):
    """(tag, attributes text, {id, model}) of each record/template/menuitem with an id."""
    for source in _xml_sources(module) or ():
        for tag, attrs in _RECORD.findall(source):
            values = {name: double or single for name, double, single in _ATTR.findall(attrs)}
            if values.get("id"):
                yield tag, attrs, values


def _xml_records_of(module):
    """{xmlid: model} declared by the module's 20.0 XML files."""
    records = {}
    for tag, _attrs, values in _xml_tags_of(module):
        model = values.get("model") if tag == "record" else _TAG_MODEL[tag]
        if model:
            records[_qualified(module, values["id"])] = model
    return records


def _standalone_templates_of(module):
    """xmlids of the module's 20.0 <template> tags that declare no inherit_id."""
    return {
        _qualified(module, values["id"])
        for tag, attrs, values in _xml_tags_of(module)
        if tag == "template" and "inherit_id=" not in attrs
    }


def _detach_templates_now_standalone(cr):
    """website_sale.suggested_products_list extends cart_lines in 19.0 and is a standalone
    template in 20.0. The <template> loader writes inherit_id only when the XML gives one, so
    the 19.0 parent stays and the view fails ("cannot be located in parent view")."""
    cr.execute("SELECT name FROM ir_module_module WHERE state IN ('installed', 'to upgrade')")
    standalone = set()
    for (module,) in cr.fetchall():
        standalone |= _standalone_templates_of(module)
    cr.execute("""SELECT d.module || '.' || d.name, v.id FROM ir_model_data d
             JOIN ir_ui_view v ON v.id = d.res_id
            WHERE d.model = 'ir.ui.view' AND v.inherit_id IS NOT NULL""")
    ids = [view_id for xmlid, view_id in cr.fetchall() if xmlid in standalone]
    if ids:
        openupgrade.logged_query(
            cr, "UPDATE ir_ui_view SET inherit_id = NULL, mode = 'primary' WHERE id = ANY(%s)", [ids]
        )


def _release_xmlids_that_changed_model(cr):
    """`mass_mailing.mailing_list_merge_action` is an act_window in 19.0 and a server action in
    20.0: loading the file fails with "found record of different model"."""
    cr.execute("SELECT name FROM ir_module_module WHERE state IN ('installed', 'to upgrade')")
    declared = {}
    for (module,) in cr.fetchall():
        declared.update(_xml_records_of(module))
    cr.execute("SELECT id, module, name, model, res_id FROM ir_model_data WHERE module NOT LIKE '\\_\\_%%'")
    for data_id, module, name, model, res_id in cr.fetchall():
        new_model = declared.get(f"{module}.{name}")
        if not new_model or new_model == model or RENAMED_MODELS.get(model) == new_model:
            continue
        cr.execute("DELETE FROM ir_model_data WHERE id = %s", [data_id])
        if model in _TECHNICAL:
            table = {
                "ir.actions.act_window": "ir_act_window",
                "ir.actions.server": "ir_act_server",
                "ir.actions.client": "ir_act_client",
                "ir.actions.report": "ir_act_report_xml",
                "ir.actions.act_url": "ir_act_url",
                "ir.ui.menu": "ir_ui_menu",
                "ir.cron": "ir_cron",
            }[model]
            cr.execute(f"DELETE FROM {table} WHERE id = %s", [res_id])
        openupgrade.logger.info("xmlid %s.%s: %s -> %s, old record released", module, name, model, new_model)


def _install_new_auto_install_modules(cr):
    cr.execute("SELECT name FROM ir_module_module WHERE state = 'installed'")
    installed = {name for (name,) in cr.fetchall()}
    for module, depends in NEW_AUTO_INSTALL.items():
        if not all(dep in installed for dep in depends):
            continue
        cr.execute("SELECT state FROM ir_module_module WHERE name = %s", [module])
        row = cr.fetchone()
        if row is None:
            openupgrade.logged_query(
                cr,
                """INSERT INTO ir_module_module (name, state, demo, create_uid, write_uid, create_date, write_date)
                   VALUES (%s, 'to install', FALSE, 1, 1, now() at time zone 'UTC', now() at time zone 'UTC')""",
                [module],
            )
        elif row[0] == "uninstalled":
            openupgrade.logged_query(cr, "UPDATE ir_module_module SET state = 'to install' WHERE name = %s", [module])


def _deactivate_obsolete_views(cr):
    """A 19.0 view that 20.0 no longer ships stays active while its module loads and breaks the
    validation of the views it extends (mail.ir_cron_view_form: mail_post_method). Odoo removes
    obsolete records only after the module is loaded. Deactivate them first; the end of the
    upgrade deletes those that are not noupdate. website/theme templates are generated in code
    and website.page views carry auto `*_ir_ui_view` ids, so they are left alone.
    Every deactivated view is listed in `openupgrade_legacy_20_0_deactivated_view` for review."""
    cr.execute("""
        SELECT d.module, d.name, d.res_id FROM ir_model_data d
          JOIN ir_ui_view v ON v.id = d.res_id
          JOIN ir_module_module m ON m.name = d.module AND m.state IN ('installed', 'to upgrade')
         WHERE d.model = 'ir.ui.view' AND v.active
           AND d.module != 'website' AND d.module NOT LIKE 'theme\\_%%'
           AND d.name NOT LIKE '%%\\_ir\\_ui\\_view'
        """)
    defined, obsolete = {}, []
    for module, name, view_id in cr.fetchall():
        if module not in defined:
            defined[module] = _xml_ids_of(module)
        if defined[module] is not None and f"{module}.{name}" not in defined[module]:
            obsolete.append((module, name, view_id))
    cr.execute("""CREATE TABLE IF NOT EXISTS openupgrade_legacy_20_0_deactivated_view
           (view_id integer, module varchar, name varchar)""")
    if obsolete:
        cr.execute(
            "INSERT INTO openupgrade_legacy_20_0_deactivated_view VALUES " + ",".join(["(%s,%s,%s)"] * len(obsolete)),
            [value for module, name, view_id in obsolete for value in (view_id, module, name)],
        )
        openupgrade.logged_query(
            cr, "UPDATE ir_ui_view SET active = FALSE WHERE id = ANY(%s)", [[o[2] for o in obsolete]]
        )
        # their website-specific copies (same key, website_id set, no xmlid) go with them
        openupgrade.logged_query(
            cr,
            """UPDATE ir_ui_view SET active = FALSE
                WHERE website_id IS NOT NULL AND active AND key = ANY(%s)
            RETURNING id""",
            [[f"{module}.{name}" for module, name, _id in obsolete]],
        )


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    _drop_views_of_merged_modules(cr)
    _deactivate_obsolete_views(cr)
    _free_acl_xmlids(cr)
    _release_xmlids_that_changed_model(cr)
    _detach_templates_now_standalone(cr)
    _install_new_auto_install_modules(cr)
    openupgrade.update_module_names(cr, RENAMED_MODULES.items())
    openupgrade.update_module_names(cr, MERGED_MODULES.items(), merge_modules=True)
    openupgrade.rename_xmlids(cr, XMLID_RENAMES)
    _fold_res_bank_into_partner_bank(cr)
    for _model, table, old, new in PARTNER_BANK_FIELDS:
        if openupgrade.column_exists(cr, table, old):
            openupgrade.rename_columns(cr, {table: [(old, new)]})
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_model_fields SET name = CASE name
            WHEN 'acc_number' THEN 'account_number'
            WHEN 'sanitized_acc_number' THEN 'sanitized_account_number'
            WHEN 'acc_holder_name' THEN 'holder_name' END
         WHERE model = 'res.partner.bank'
           AND name IN ('acc_number', 'sanitized_acc_number', 'acc_holder_name')
        """,
    )
