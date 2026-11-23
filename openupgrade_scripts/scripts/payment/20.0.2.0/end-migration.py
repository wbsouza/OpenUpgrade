# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of payment.

19.0 had one global catalog of payment methods shared by providers (m2m provider_ids). In
20.0 every method belongs to one provider (provider_id, required, unique with code), and each
provider module ships its own methods. The 19.0 catalog rows are noupdate, so they survive
the upgrade with no provider while tokens and transactions still point at them (a token
of any provider saved on the 19.0 `card` method, for instance).

For every method without a provider:
1. per provider that uses it in tokens/transactions: repoint those rows to the provider's
   20.0 method with the same code; if the provider has none, the old method becomes its own;
2. an active method with exactly one 19.0 provider is kept for that provider;
3. anything else is unused and deleted.

Finally every provider's method gets the 19.0 state of the catalog method with its code for
that provider. 20.0 provider modules create their methods inactive (active NULL) and activate
them only when the provider is enabled (`_activate_default_pms`), which a provider already
enabled on 19.0 never is again: it would offer no payment method at all.
"""

from openupgradelib import openupgrade


def _users(cr, method_id):
    cr.execute(
        """SELECT provider_id FROM payment_token WHERE payment_method_id = %(m)s
           UNION SELECT provider_id FROM payment_transaction WHERE payment_method_id = %(m)s""",
        {"m": method_id},
    )
    return [provider_id for (provider_id,) in cr.fetchall() if provider_id]


def _repoint(cr, old_id, new_id, provider_id):
    for table in ("payment_token", "payment_transaction"):
        openupgrade.logged_query(
            cr,
            f"UPDATE {table} SET payment_method_id = %s WHERE payment_method_id = %s AND provider_id = %s",
            [new_id, old_id, provider_id],
        )


def active_on_19(cr):
    """(provider_id, code) of every 19.0 catalog method that was active for that provider (the 19.0
    m2m provider_ids, a table 20.0 no longer manages)."""
    if not openupgrade.table_exists(cr, "payment_method_payment_provider_rel"):
        return []
    cr.execute("""SELECT DISTINCT rel.payment_provider_id, pm.code
                    FROM payment_method pm
                    JOIN payment_method_payment_provider_rel rel ON rel.payment_method_id = pm.id
                   WHERE pm.active""")
    return cr.fetchall()


def mirror_activation(cr, pairs):
    """Activate each provider's method of a code active for it on 19.0; every other method of
    unknown state (NULL) is inactive, as Odoo reads it."""
    if pairs:
        openupgrade.logged_query(
            cr,
            """UPDATE payment_method pm SET active = TRUE
                 FROM unnest(%s::int[], %s::varchar[]) AS old(provider_id, code)
                WHERE pm.provider_id = old.provider_id AND pm.code = old.code AND pm.active IS NOT TRUE""",
            [[provider_id for provider_id, _code in pairs], [code for _provider_id, code in pairs]],
        )
    openupgrade.logged_query(cr, "UPDATE payment_method SET active = FALSE WHERE active IS NULL")


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    # before the catalog rows (and their provider links, ON DELETE CASCADE) are removed below
    enabled = active_on_19(cr)
    cr.execute("SELECT id, code, active FROM payment_method WHERE provider_id IS NULL")
    orphans = cr.fetchall()
    for method_id, code, active in orphans:
        for provider_id in _users(cr, method_id):
            cr.execute("SELECT id FROM payment_method WHERE provider_id = %s AND code = %s", [provider_id, code])
            row = cr.fetchone()
            if row:
                _repoint(cr, method_id, row[0], provider_id)
            else:
                cr.execute("SELECT provider_id FROM payment_method WHERE id = %s", [method_id])
                if cr.fetchone()[0] is None:
                    openupgrade.logged_query(
                        cr, "UPDATE payment_method SET provider_id = %s WHERE id = %s", [provider_id, method_id]
                    )
        cr.execute("SELECT provider_id FROM payment_method WHERE id = %s", [method_id])
        if cr.fetchone()[0] is None and active:
            cr.execute(
                "SELECT payment_provider_id FROM payment_method_payment_provider_rel WHERE payment_method_id = %s",
                [method_id],
            )
            providers = [p for (p,) in cr.fetchall()]
            if len(providers) == 1:
                openupgrade.logged_query(
                    cr, "UPDATE payment_method SET provider_id = %s WHERE id = %s", [providers[0], method_id]
                )
    cr.execute("""SELECT id FROM payment_method pm WHERE provider_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM payment_token t WHERE t.payment_method_id = pm.id)
            AND NOT EXISTS (SELECT 1 FROM payment_transaction t WHERE t.payment_method_id = pm.id)""")
    unused = [method_id for (method_id,) in cr.fetchall()]
    if unused:
        openupgrade.logged_query(
            cr,
            "UPDATE payment_method SET primary_payment_method_id = NULL WHERE primary_payment_method_id = ANY(%s)",
            [unused],
        )
        openupgrade.logged_query(
            cr, "DELETE FROM ir_model_data WHERE model = 'payment.method' AND res_id = ANY(%s)", [unused]
        )
        openupgrade.logged_query(cr, "DELETE FROM payment_method WHERE id = ANY(%s)", [unused])
    mirror_activation(cr, enabled)
    env.invalidate_all()
