# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of website_sale.

Scheduled actions moved without an xmlid rename. On 19.0,
``website_sale.ir_cron_send_availability_email`` is the abandoned-cart cron
(``website._send_abandoned_cart_email``) and the product availability cron is
``website_sale_stock.ir_cron_send_availability_email``. 20.0 names the abandoned-cart
cron ``website_sale.ir_cron_send_abandoned_email`` (``_cron_send_abandoned_cart_email``)
and gives ``website_sale.ir_cron_send_availability_email`` to the availability cron
(``product.product._send_availability_email``, now in website_sale).

``ir_cron_data.xml`` is noupdate: left as is, the abandoned-cart cron kept the
availability xmlid and its 19.0 code (AttributeError on every run), the availability
cron was deleted and a second abandoned-cart cron was created. The xmlids are moved so
both 19.0 records keep their id, schedule and active state, and the abandoned-cart
code calls the 20.0 method.

``website.send_abandoned_cart_email`` is renamed ``send_abandoned_cart_followup``.
"""

from openupgradelib import openupgrade

# in this order: the abandoned-cart cron frees the name the availability cron takes
CRON_XMLIDS = [
    (
        "website_sale.ir_cron_send_availability_email",
        "website_sale.ir_cron_send_abandoned_email",
    ),
    (
        "website_sale_stock.ir_cron_send_availability_email",
        "website_sale.ir_cron_send_availability_email",
    ),
]


def _xmlid_exists(cr, xmlid):
    cr.execute(
        "SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s",
        xmlid.split("."),
    )
    return bool(cr.rowcount)


def _rename_crons(cr):
    for old, new in CRON_XMLIDS:
        if not _xmlid_exists(cr, old) or _xmlid_exists(cr, new):
            continue
        action_old, action_new = f"{old}_ir_actions_server", f"{new}_ir_actions_server"
        openupgrade.rename_xmlids(cr, [(old, new), (action_old, action_new)])
        # noupdate, as on a fresh 20.0 database
        module, name = new.split(".")
        openupgrade.logged_query(
            cr,
            "UPDATE ir_model_data SET noupdate = TRUE"
            " WHERE module = %s AND name IN (%s, %s)",
            [module, name, action_new.split(".")[1]],
        )
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_act_server s
           SET code = replace(s.code, '._send_abandoned_cart_email(',
                              '._cron_send_abandoned_cart_email(')
          FROM ir_model m
         WHERE m.id = s.model_id AND m.model = 'website' AND s.state = 'code'
           AND s.code LIKE %s
        """,
        ["%._send_abandoned_cart_email(%"],
    )


@openupgrade.migrate()
def migrate(env, version):
    _rename_crons(env.cr)
    if openupgrade.column_exists(env.cr, "website", "send_abandoned_cart_email"):
        openupgrade.rename_fields(
            env,
            [
                (
                    "website",
                    "website",
                    "send_abandoned_cart_email",
                    "send_abandoned_cart_followup",
                )
            ],
        )
