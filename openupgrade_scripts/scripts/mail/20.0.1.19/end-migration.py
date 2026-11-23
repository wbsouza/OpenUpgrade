# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of mail.

- Compute `mail.activity.phone`, left empty by pre-migration.
- Noupdate mail templates of the core modules keep their 19.0 body, which can call APIs removed in
  20.0 (they then fail to render: no invitation, no recruitment mail). A template still exactly as
  its 19.0 module shipped it (fingerprint of its text fields) is reloaded from its 20.0 source, every
  installed language included. Any other one (customised, or older than 19.0) only gets the removed
  calls replaced by their 20.0 equivalent; nothing else in it changes. Obsolete templates 20.0
  replaced are removed.
- Replace the web push (VAPID) key pair: the 19.0 keys and the browsers subscribed with them are
  removed and a new pair is generated, so nothing is tied to the old keys. A browser that still
  holds an old subscription is refused once, then subscribes again with the new key.
  Idempotent: each run leaves exactly one fresh pair and no stale subscription. Neutralize later
  drops the pair on test copies; Odoo generates another on the first visit.
"""

import hashlib
import json
import logging
import re

from lxml import etree, html
from openupgradelib import openupgrade

from odoo.tools.convert import xml_import
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

VAPID_KEYS = ("mail.web_push_vapid_private_key", "mail.web_push_vapid_public_key")


@openupgrade.migrate()
def migrate(env, version):
    refresh_noupdate_templates(env)
    activities = env["mail.activity"].with_context(active_test=False).search([])
    activities = activities.filtered(lambda a: a.res_model in env)
    env.add_to_compute(activities._fields["phone"], activities)
    activities.flush_recordset(["phone"])

    devices = env["mail.push.device"].sudo().search([])
    keys = env["ir.config_parameter"].sudo().search([("key", "in", VAPID_KEYS)])
    devices.unlink()
    keys.unlink()
    env["mail.push.device"].get_web_push_vapid_public_key()  # generates the new pair
    _logger.info("web push reset: %d subscribed browsers and %d VAPID keys replaced", len(devices), len(keys))


# Text fields a 19.0 template file sets: equal (as text, markup compared as HTML) = never customised
FINGERPRINT_FIELDS = (
    "name", "subject", "body_html", "email_from", "email_to", "email_cc", "partner_to", "reply_to", "lang",
    "scheduled_date",
)
# xmlid: fingerprint of the record in its 19.0 file, for every core template whose 20.0 body differs
TEMPLATES_19 = {
    "account.email_template_edi_invoice": "c0c083a7d6951948",
    "account.email_template_edi_self_billing_invoice": "7ed9e0460ae970b5",
    "account.mail_template_data_payment_receipt": "0c9329a89a1b3692",
    "auth_signup.mail_template_data_unregistered_users": "26e3c8cd2a26a239",
    "auth_signup.mail_template_user_signup_account_created": "bb17c04606a9cb84",
    "auth_signup.portal_set_password_email": "21aff6299637aa49",
    "auth_signup.set_password_email": "6825146f310bbf23",
    "auth_totp_mail.mail_template_totp_mail_code": "c524aa4958b86759",
    "calendar.calendar_template_delete_event": "1a7d511c8b532cc9",
    "calendar.calendar_template_meeting_changedate": "9242e6cd09976cff",
    "calendar.calendar_template_meeting_invitation": "1dc88156e76f384f",
    "calendar.calendar_template_meeting_reminder": "c0534810c4674f22",
    "calendar.calendar_template_meeting_update": "a00a08ce811bb527",
    "crm.mail_template_demo_crm_lead": "5e6f4bd12a07d85f",
    "gamification.email_template_badge_received": "35563838e8fe6556",
    "hr_recruitment.email_template_data_applicant_congratulations": "1c6c3f334c6a7286",
    "hr_recruitment.email_template_data_applicant_interest": "3c48c8f9d94c485c",
    "hr_recruitment.email_template_data_applicant_not_interested": "79e685bc71be448c",
    "hr_recruitment.email_template_data_applicant_refuse": "3ee28a356f377272",
    "loyalty.mail_template_gift_card": "52be846a5ebc9af5",
    "loyalty.mail_template_loyalty_card": "6d72a5ea721117bc",
    "lunch.lunch_order_mail_supplier": "305e3dc233ba33e5",
    "pos_self_order.delivery_email_template": "c055406f76ada99d",
    "pos_self_order.takeout_email_template": "1aa8059d7b4806c3",
    "purchase.email_template_edi_purchase": "f3319e50d60e94f3",
    "sale.email_template_edi_sale": "d845ac90b095914c",
    "sale.email_template_proforma": "f88cee9e6261d7e3",
    "sale.mail_template_sale_confirmation": "83ccf6d02d90ac36",
    "stock.mail_template_data_delivery_confirmation": "6345d17257215475",
    "website_crm_partner_assign.email_template_lead_forward_mail": "aca5e3a16fa33ed7",
    "website_event_track.mail_template_data_track_reminder": "c4a4bebb2a6076aa",
    "website_profile.validation_email": "b05c155b099232de",
    "website_sale.mail_template_sale_cart_recovery": "539b0504bacb56ab",
    "website_slides.mail_template_slide_channel_enroll": "f9bf64d383d737cc",
    "website_slides.mail_template_slide_channel_invite": "b51584fc52c00794",
}
# replaced in 20.0 by a QWeb view; only rendered with a context 20.0 no longer passes
OBSOLETE_TEMPLATES = ["base_install_request.mail_template_base_install_request"]


def _normalized(field, value):
    value = value or ""
    if field != "body_html" or not value.strip():
        return " ".join(value.split())
    root = html.fragment_fromstring(value, create_parent="div", parser=html.HTMLParser(remove_comments=True))
    for node in root.iter():
        node.text = " ".join(node.text.split()) or None if node.text else None
        node.tail = " ".join(node.tail.split()) or None if node.tail else None
    return etree.tostring(root, method="html", encoding="unicode")


def fingerprint(values):
    """Short hash of the template's text fields (`values`: field name -> en_US text)."""
    data = json.dumps([_normalized(name, values.get(name)) for name in FINGERPRINT_FIELDS])
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _has(env, model, attribute):
    return model in env and attribute in dir(env[model])


# (template model, field, pattern, replacement, still valid in 20.0?): calls 20.0 removed
REMOVED_CALLS = [
    # ir.config_parameter.get_param -> typed getters (get_str keeps the string and the default)
    (None, None, r"(\['ir\.config_parameter'\](?:\.sudo\(\))?)\.get_param\(", r"\1.get_str(",
     lambda env: _has(env, "ir.config_parameter", "get_param")),
    # hr.applicant.user_id -> recruiter_id (an employee)
    ("hr.applicant", None, r"\bobject\.user_id\.email\b", "object.recruiter_id.work_email",
     lambda env: "user_id" in env["hr.applicant"]._fields),
    ("hr.applicant", None, r"\bobject\.user_id\.phone\b", "object.recruiter_id.work_phone",
     lambda env: "user_id" in env["hr.applicant"]._fields),
    ("hr.applicant", None, r"\bobject\.user_id\b", "object.recruiter_id",
     lambda env: "user_id" in env["hr.applicant"]._fields),
    # sale.order.line.product_uom -> product_uom_id (18.0)
    ("sale.order", None, r"\bline\.product_uom\.", "line.product_uom_id.",
     lambda env: "product_uom" in env["sale.order.line"]._fields),
    # calendar.event._get_attendee_emails (16.0) -> the default recipients (use_default_to)
    ("calendar.event", "email_to", r"^\s*\{\{\s*object\._get_attendee_emails\(\)\s*\}\}\s*$", "",
     lambda env: _has(env, "calendar.event", "_get_attendee_emails")),
]


def refresh_noupdate_templates(env):
    templates = env["mail.template"].with_context(active_test=False, lang="en_US").search([])
    xmlids = templates.get_external_id()
    for template in templates:
        xmlid = xmlids.get(template.id)
        if xmlid in TEMPLATES_19 and _current(template) == TEMPLATES_19[xmlid]:
            if _reload(template, xmlid):
                continue
        _patch_removed_calls(env, template, xmlid)
    openupgrade.delete_records_safely_by_xml_id(env, OBSOLETE_TEMPLATES)


def _current(template):
    values = {name: template[name] for name in FINGERPRINT_FIELDS if name in template._fields}
    return fingerprint({name: str(value) if value else "" for name, value in values.items()})


def _reload(template, xmlid):
    """Load the record from its 20.0 file, as an update would if it were not noupdate; then the
    20.0 translations of every installed language."""
    module, name = xmlid.split(".")
    records = []
    if template.template_fs:
        try:
            path = file_path(template.template_fs, filter_ext=(".xml",))
            records = etree.parse(path).xpath("//record[@id=$a or @id=$b]", a=name, b=xmlid)
        except (FileNotFoundError, ValueError):
            pass
    if not records:
        _logger.warning("mail template %s: no 20.0 source in %s, not reloaded", xmlid, template.template_fs)
        return False
    for record in records:
        xml_import(template.env, module, {}, mode="init", noupdate=True, xml_filename=path)._tag_record(record)
    template._override_translation_term(module, [name, xmlid])
    _logger.info("mail template %s (%s) untouched since 19.0: reloaded from %s", xmlid, template.id, path)
    return True


def _patch_removed_calls(env, template, xmlid):
    """Every language of the stored value is patched (translated fields are jsonb per language)."""
    for model, only_field, pattern, replacement, still_valid in REMOVED_CALLS:
        if (model and template.model != model) or still_valid(env):
            continue
        for field in [only_field] if only_field else PATCHED_FIELDS:
            env.cr.execute(f"SELECT {field} FROM mail_template WHERE id = %s", [template.id])  # field from a constant
            stored = env.cr.fetchone()[0]
            if isinstance(stored, dict):
                patched = {lang: re.sub(pattern, replacement, value or "") for lang, value in stored.items()}
                if patched == stored:
                    continue
                value = json.dumps(patched)
                env.cr.execute(f"UPDATE mail_template SET {field} = %s WHERE id = %s", [value, template.id])
            else:
                patched = re.sub(pattern, replacement, stored or "")
                if patched == (stored or ""):
                    continue
                env.cr.execute(f"UPDATE mail_template SET {field} = %s WHERE id = %s", [patched or None, template.id])
                if not patched and field == "email_to":  # 20.0's default recipients instead
                    env.cr.execute("UPDATE mail_template SET use_default_to = TRUE WHERE id = %s", [template.id])
            template.invalidate_recordset()
            _logger.info("mail template %s (%s): %s: removed call %s replaced", xmlid, template.id, field, pattern)


PATCHED_FIELDS = ("body_html", "subject", "email_from", "email_to", "email_cc", "partner_to", "reply_to", "lang")
