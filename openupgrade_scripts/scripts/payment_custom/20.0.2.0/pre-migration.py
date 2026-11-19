# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of payment_custom: 20.0 drops the view payment_custom.redirect_form,
but payment_provider.redirect_form_view_id points to it with ON DELETE RESTRICT (Wire Transfer,
Cash on Delivery), which blocks its deletion at the end of the update. Unhook those providers; the
end-migration gives them the 20.0 form."""

from openupgradelib import openupgrade


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    openupgrade.logged_query(
        cr,
        """UPDATE payment_provider p
              SET redirect_form_view_id = NULL
             FROM ir_model_data d
            WHERE d.module = 'payment_custom' AND d.name = 'redirect_form' AND d.model = 'ir.ui.view'
              AND p.redirect_form_view_id = d.res_id""",
    )
