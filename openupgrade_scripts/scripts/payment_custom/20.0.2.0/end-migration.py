# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of payment_custom: 20.0 custom providers render
payment.generic_redirect_form. The providers unhooked by the pre-migration are noupdate, so the
update does not set it."""

from openupgradelib import openupgrade


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    openupgrade.logged_query(
        cr,
        """UPDATE payment_provider p
              SET redirect_form_view_id = d.res_id
             FROM ir_model_data d
            WHERE d.module = 'payment' AND d.name = 'generic_redirect_form' AND d.model = 'ir.ui.view'
              AND p.code = 'custom' AND p.redirect_form_view_id IS NULL""",
    )
