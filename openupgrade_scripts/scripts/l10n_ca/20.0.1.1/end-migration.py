# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of l10n_ca: put the company on the 20.0 Canadian chart of accounts.

The 20.0 ``ca_2023`` template is a different chart (149 named accounts, 15 of them parents, no
codes) from the 19.0 one (351 numbered accounts + ``account.group``). A new 20.0 database gets the
new chart; an upgraded one keeps the old. This script:

1. adopts the 19.0 accounts that hold postings or serve as defaults as their 20.0
   counterparts (the xmlid is renamed, so the record, its lines and every setting pointing
   to it are kept);
2. merges the accounts left with the same role (second sales account, cash difference) into it;
3. loads the 20.0 accounts only (taxes, fiscal positions, journals and company defaults are left
   alone: the accountant decides those);
4. archives the 19.0 accounts that nothing uses.

Balances are checked before and after; the upgrade fails if they differ.
"""

import logging

from openupgradelib import openupgrade
from psycopg2 import sql

_logger = logging.getLogger(__name__)

TEMPLATE = "ca_2023"
OLD_ACCOUNT_XMLID = r"^\d+_l10n_ca_\d+$"  # 19.0 template accounts: <company>_l10n_ca_<code>
ADOPT = {  # 19.0 template account -> 20.0 template account (same record)
    # accounts with postings
    "l10n_ca_112110": "l10n_ca_accounts_receivable",
    "l10n_ca_411100": "l10n_ca_sales_revenue",
    "l10n_ca_231000": "l10n_ca_gst_received",
    "l10n_ca_232000": "l10n_ca_pst_received",
    "l10n_ca_233000": "l10n_ca_hst_received",
    # accounts used as defaults (company, partners, product categories, cash journal): the 20.0
    # account holding the same role in l10n_ca/models/template_ca.py
    "l10n_ca_112113": "l10n_ca_accounts_receivable_pos",
    "l10n_ca_121120": "l10n_ca_inventory_valuation",
    "l10n_ca_221110": "l10n_ca_accounts_payable",
    "l10n_ca_511210": "l10n_ca_cost_of_goods_sold",
    "l10n_ca_423100": "l10n_ca_foreign_exchange_gain",
    "l10n_ca_522100": "l10n_ca_foreign_exchange_loss",
    "l10n_ca_423200": "l10n_ca_cash_discount_gain",
    "l10n_ca_522200": "l10n_ca_cash_discount_loss",
    "l10n_ca_615000": "l10n_ca_cash_difference_gain",
    "l10n_ca_613000": "l10n_ca_cash_difference_loss",
    # accounts Odoo created outside the template, holding a role the 20.0 template covers
    "transfer_account_id": "l10n_ca_funds_in_transfers",
    "account_journal_suspense_account_id": "l10n_ca_bank_suspense_account",
}
MERGE = {  # source account -> 20.0 account, after ADOPT
    "l10n_ca_411000": "l10n_ca_sales_revenue",
    "default_cash_difference_income_account_id": "l10n_ca_cash_difference_gain",
    "default_cash_difference_expense_account_id": "l10n_ca_cash_difference_loss",
}
# relation tables describing the account itself, not a use of it
OWN_TABLES = {"account_account", "account_account_res_company_rel", "account_account_account_tag"}


def _account_refs(cr):
    """Every column that stores an account id: (table, column, is_jsonb)."""
    cr.execute("""
        SELECT c.conrelid::regclass::text, a.attname
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.confrelid = 'account_account'::regclass AND c.contype = 'f'
        """)
    refs = [(t, c, False) for t, c in cr.fetchall() if t not in OWN_TABLES]
    cr.execute("""
        SELECT m.model, f.name FROM ir_model_fields f JOIN ir_model m ON m.id = f.model_id
         WHERE f.company_dependent AND f.relation = 'account.account' AND f.store
        """)
    for model, fname in cr.fetchall():
        table = model.replace(".", "_")
        if openupgrade.column_exists(cr, table, fname):
            refs.append((table, fname, True))
    return refs


def _used_account_ids(cr, refs):
    """Accounts referenced anywhere, except by the repartition lines of archived taxes."""
    used = set()
    for table, column, is_jsonb in refs:
        if is_jsonb:
            query = sql.SQL(
                "SELECT DISTINCT v::int FROM {t}, jsonb_each_text({c}) AS e(k, v) WHERE v ~ '^\\d+$'"
            ).format(t=sql.Identifier(table), c=sql.Identifier(column))
        elif table == "account_tax_repartition_line":
            query = sql.SQL(
                "SELECT DISTINCT r.account_id FROM account_tax_repartition_line r"
                " JOIN account_tax t ON t.id = r.tax_id WHERE t.active AND r.account_id IS NOT NULL"
            )
        else:
            query = sql.SQL("SELECT DISTINCT {c} FROM {t} WHERE {c} IS NOT NULL").format(
                t=sql.Identifier(table), c=sql.Identifier(column)
            )
        cr.execute(query)
        used.update(r[0] for r in cr.fetchall())
    cr.execute(
        "SELECT json_value FROM ir_default d JOIN ir_model_fields f ON f.id = d.field_id"
        " WHERE f.relation = 'account.account'"
    )
    used.update(int(v) for (v,) in cr.fetchall() if v and v.isdigit())
    return used


def _repoint(cr, refs, old_id, new_id):
    """Move every use of account ``old_id`` to ``new_id``."""
    for table, column, is_jsonb in refs:
        t, c = sql.Identifier(table), sql.Identifier(column)
        if is_jsonb:
            cr.execute(
                sql.SQL(
                    "UPDATE {t} SET {c} = (SELECT jsonb_object_agg(k, CASE WHEN v = to_jsonb(%(old)s)"
                    " THEN to_jsonb(%(new)s) ELSE v END) FROM jsonb_each({c}) AS e(k, v))"
                    " WHERE {c} @? '$.* ? (@ == %(old)s)'"
                ).format(t=t, c=c),
                {"old": old_id, "new": new_id},
            )
            continue
        if not openupgrade.column_exists(cr, table, "id"):  # many2many: drop pairs that would duplicate
            cr.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND column_name != %s",
                [table, column],
            )
            others = [sql.Identifier(r[0]) for r in cr.fetchall()]
            same = sql.SQL(" AND ").join(sql.SQL("o.{x} = n.{x}").format(x=x) for x in others)
            cr.execute(
                sql.SQL(
                    "DELETE FROM {t} o WHERE o.{c} = %(old)s AND EXISTS"
                    " (SELECT 1 FROM {t} n WHERE n.{c} = %(new)s AND {same})"
                ).format(t=t, c=c, same=same),
                {"old": old_id, "new": new_id},
            )
        cr.execute(sql.SQL("UPDATE {t} SET {c} = %s WHERE {c} = %s").format(t=t, c=c), [new_id, old_id])
    cr.execute(
        "UPDATE ir_default d SET json_value = %s FROM ir_model_fields f"
        " WHERE f.id = d.field_id AND f.relation = 'account.account' AND d.json_value = %s",
        [str(new_id), str(old_id)],
    )


def _merge_into(cr, refs, old_id, new_id):
    """Move every use of ``old_id`` to ``new_id`` and archive the emptied account."""
    _repoint(cr, refs, old_id, new_id)
    cr.execute("UPDATE account_account SET active = FALSE WHERE id = %s", [old_id])


def _balances(cr):
    cr.execute("SELECT account_id, round(sum(debit), 2), round(sum(credit), 2) FROM account_move_line GROUP BY 1")
    return {a: (d, c) for a, d, c in cr.fetchall()}


def _xmlid_id(cr, name):
    cr.execute("SELECT res_id FROM ir_model_data WHERE module = 'account' AND name = %s", [name])
    row = cr.fetchone()
    return row and row[0]


def _adopt(cr, company_id, refs):
    """Rename the xmlids of the 19.0 accounts we keep; returns {old account id: kept account id}."""
    merged = {}
    for old, new in ADOPT.items():
        old_name, new_name = f"{company_id}_{old}", f"{company_id}_{new}"
        old_id, new_id = _xmlid_id(cr, old_name), _xmlid_id(cr, new_name)
        if not old_id:
            continue
        if new_id:  # 20.0 account already there: merge the old one into it
            _merge_into(cr, refs, old_id, new_id)
            merged[old_id] = new_id
            continue
        cr.execute(
            "UPDATE ir_model_data SET name = %s, noupdate = TRUE WHERE module = 'account' AND name = %s",
            [new_name, old_name],
        )
        _logger.info("l10n_ca: account %s adopted as %s", old_name, new_name)
    return merged


def _merge(cr, company_id, refs):
    merged = {}
    for old, new in MERGE.items():
        old_id, new_id = _xmlid_id(cr, f"{company_id}_{old}"), _xmlid_id(cr, f"{company_id}_{new}")
        if old_id and new_id:
            _merge_into(cr, refs, old_id, new_id)
            merged[old_id] = new_id
            _logger.info("l10n_ca: account %s_%s merged into %s_%s", company_id, old, company_id, new)
    return merged


def _load_accounts(env, company):
    chart = env["account.chart.template"].with_company(company).with_context(ignore_missing_tags=True)
    accounts = chart._get_chart_template_data(TEMPLATE)["account.account"]
    for vals in accounts.values():
        vals.pop("tax_ids", None)  # default taxes stay as they are: the accountant decides
    chart._load_data({"account.account": accounts})
    chart._load_translations(companies=company, template_data={"account.account": accounts})
    return len(accounts)


def _archive_unused(cr, company_id, refs):
    used = _used_account_ids(cr, refs)
    cr.execute(
        """
        SELECT a.id FROM account_account a
          JOIN ir_model_data d ON d.model = 'account.account' AND d.res_id = a.id AND d.module = 'account'
         WHERE a.active AND d.name ~ %s AND d.name LIKE %s
        """,
        [OLD_ACCOUNT_XMLID, f"{company_id}\\_%"],
    )
    unused = [a for (a,) in cr.fetchall() if a not in used]
    if unused:
        cr.execute("UPDATE account_account SET active = FALSE WHERE id = ANY(%s)", [unused])
    return len(unused)


def _check_balances(before, after, merged):
    expected = {}
    for account, (debit, credit) in before.items():
        target = merged.get(account, account)
        d, c = expected.get(target, (0, 0))
        expected[target] = (d + debit, c + credit)
    wrong = {a: (expected.get(a), after.get(a)) for a in set(expected) | set(after) if expected.get(a) != after.get(a)}
    if wrong:
        raise RuntimeError(f"l10n_ca chart migration changed account balances: {wrong}")


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    companies = env["res.company"].search([("chart_template", "=", TEMPLATE)])
    if not companies:
        return
    refs = _account_refs(cr)
    before = _balances(cr)
    merged = {}
    for company in companies:
        merged |= _adopt(cr, company.id, refs)
        merged |= _merge(cr, company.id, refs)
        env.invalidate_all()
        loaded = _load_accounts(env, company)
        env.flush_all()
        archived = _archive_unused(cr, company.id, refs)
        _logger.info(
            "l10n_ca: %s: %d chart accounts loaded, %d unused 19.0 accounts archived", company.name, loaded, archived
        )
    env.invalidate_all()
    _check_balances(before, _balances(cr), merged)
