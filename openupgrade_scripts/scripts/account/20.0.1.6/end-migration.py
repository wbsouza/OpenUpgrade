# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 end-migration of account: payments left in the dropped ``in_process`` state.

19.0 ``in_process`` = posted, not yet matched. 20.0 has no such state: a posted payment is
``paid``, and ``reconciled`` once its liquidity line is matched or its invoices are paid. The
payments are set to ``paid`` and core's ``_compute_state`` decides between the two.
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    env.cr.execute("UPDATE account_payment SET state = 'paid' WHERE state = 'in_process' RETURNING id")
    payments = env["account.payment"].browse(row[0] for row in env.cr.fetchall())
    env.add_to_compute(payments._fields["state"], payments)
    payments.flush_recordset(["state"])
    _logger.info(
        "UPGRADE20 %s in_process payments -> paid %s, reconciled %s",
        len(payments),
        len(payments.filtered(lambda p: p.state == "paid")),
        len(payments.filtered(lambda p: p.state == "reconciled")),
    )
