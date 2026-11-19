# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of sale.

`product.template.sale_delay` (an integer of stock in 19.0) is a company_dependent field of
sale in 20.0, stored as jsonb {company_id: value}. Postgres cannot cast integer to jsonb, so
convert it here: the default (0) becomes NULL, any other value is set for every company.
"""

from openupgradelib import openupgrade


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    cr.execute("""SELECT data_type FROM information_schema.columns
            WHERE table_name = 'product_template' AND column_name = 'sale_delay'""")
    row = cr.fetchone()
    if not row or row[0] == "jsonb":
        return
    openupgrade.logged_query(cr, "ALTER TABLE product_template ADD COLUMN sale_delay_jsonb jsonb")
    openupgrade.logged_query(
        cr,
        """
        UPDATE product_template t
           SET sale_delay_jsonb = (SELECT jsonb_object_agg(c.id::text, t.sale_delay) FROM res_company c)
         WHERE COALESCE(t.sale_delay, 0) != 0
        """,
    )
    openupgrade.logged_query(cr, "ALTER TABLE product_template DROP COLUMN sale_delay")
    openupgrade.logged_query(cr, "ALTER TABLE product_template RENAME COLUMN sale_delay_jsonb TO sale_delay")
