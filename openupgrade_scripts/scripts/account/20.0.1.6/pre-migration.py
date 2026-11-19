# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of account.

The stock valuation report moved from stock_account to account
(OpenUpgrade apriori: stock_account.stock.valuation.report -> account.stock.valuation.report).
"""

from openupgradelib import openupgrade


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    openupgrade.rename_models(cr, [("stock_account.stock.valuation.report", "account.stock.valuation.report")])
    openupgrade.rename_xmlids(
        cr, [("stock_account.action_report_stock_valuation", "account.action_report_stock_valuation")]
    )
