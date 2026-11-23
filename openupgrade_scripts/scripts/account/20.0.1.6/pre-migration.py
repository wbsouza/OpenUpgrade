# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of account.

The stock valuation report moved from stock_account to account
(OpenUpgrade apriori: stock_account.stock.valuation.report -> account.stock.valuation.report).

So did the "Inventory Valuation Closing" cron, without an xmlid rename: the 19.0
``stock_account.ir_cron_post_stock_valuation`` (noupdate) was kept and 20.0 created
``account.ir_cron_post_stock_valuation`` next to it, both calling
``res.company._cron_post_stock_valuation()``: the closing could run twice. The
19.0 record takes the 20.0 xmlid (keeping its id, schedule and active state) and,
as on a fresh 20.0 database, is updatable (``service_cron.xml`` is not noupdate).
"""

from openupgradelib import openupgrade

CRON_OLD = "stock_account.ir_cron_post_stock_valuation"
CRON_NEW = "account.ir_cron_post_stock_valuation"


def _xmlid_exists(cr, xmlid):
    cr.execute(
        "SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s",
        xmlid.split("."),
    )
    return bool(cr.rowcount)


def _move_stock_valuation_cron(cr):
    if not _xmlid_exists(cr, CRON_OLD) or _xmlid_exists(cr, CRON_NEW):
        return
    action_old = f"{CRON_OLD}_ir_actions_server"
    action_new = f"{CRON_NEW}_ir_actions_server"
    openupgrade.rename_xmlids(cr, [(CRON_OLD, CRON_NEW), (action_old, action_new)])
    openupgrade.logged_query(
        cr,
        "UPDATE ir_model_data SET noupdate = FALSE"
        " WHERE module = 'account' AND name IN (%s, %s)",
        [CRON_NEW.split(".")[1], action_new.split(".")[1]],
    )


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    openupgrade.rename_models(cr, [("stock_account.stock.valuation.report", "account.stock.valuation.report")])
    openupgrade.rename_xmlids(
        cr, [("stock_account.action_report_stock_valuation", "account.action_report_stock_valuation")]
    )
    _move_stock_valuation_cron(cr)
