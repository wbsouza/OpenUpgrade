# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Loaded with --load=base,rpc,web,openupgrade_framework for the 19.0 -> 20.0 upgrade only.

During -u all a view is validated while its module loads, combined with views whose stored
arch is still 19.0 (rewritten only when their own file is loaded later). A failing validation
is logged as a warning instead of aborting, and the view is queued in
`openupgrade_legacy_20_0_deferred_view`. base end-migration re-validates the queue with every
module loaded and logs an ERROR for each view that is still invalid.
"""

import logging

from odoo.addons.base.models.ir_ui_view import IrUiView

_logger = logging.getLogger(__name__)
_check_xml = IrUiView._check_xml

QUEUE = "openupgrade_legacy_20_0_deferred_view"


def _deferred_check_xml(self):
    for view in self:
        try:
            with self.env.cr.savepoint():
                _check_xml(view)
        except Exception as error:  # noqa: BLE001 - every validation error is deferred
            _logger.warning("OpenUpgrade: deferred view %s (%s): %s", view.id, view.xml_id, str(error).splitlines()[0])
            self.env.cr.execute(f"CREATE TABLE IF NOT EXISTS {QUEUE} (view_id integer PRIMARY KEY)")
            self.env.cr.execute(f"INSERT INTO {QUEUE} VALUES (%s) ON CONFLICT DO NOTHING", [view.id])
    return True


IrUiView._check_xml = _deferred_check_xml
IrUiView._openupgrade_check_xml = _check_xml
