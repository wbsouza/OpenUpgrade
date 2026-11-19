# Copyright 2026 Gladistone Souza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""19.0 -> 20.0 pre-migration of stock: selection values 20.0 renamed or dropped.

- ``product.template.tracking``: 19.0 stored ``'none'`` ("By Quantity"); 20.0 has only ``lot`` and
  ``serial`` and stores False, ``store_by`` deriving quantity/untracked from ``is_storable``. Left
  as ``'none'``, every product read crashed: ``_compute_store_by`` assigns it to ``store_by``
  ("Wrong value for product.template.store_by: 'none'").
- ``stock.picking.type.product_label_format``: 20.0 prefixes the barcode kind (``barcode_``/``qr_``)
  and renamed the price suffix (``2x7xprice`` -> ``barcode_2x7_price``).
"""

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

PRODUCT_LABEL_FORMATS = {
    "dymo": "barcode_dymo",
    "2x7xprice": "barcode_2x7_price",
    "4x7xprice": "barcode_4x7_price",
    "4x12": "barcode_4x12",
    "4x12xprice": "barcode_4x12_price",
    "zpl": "barcode_zpl_normal",
    "zplxprice": "barcode_zpl_normal_price",
}


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    cr.execute("UPDATE product_template SET tracking = NULL WHERE tracking = 'none'")
    _logger.info("UPGRADE20 product tracking 'none' -> NULL on %s templates", cr.rowcount)
    for old, new in PRODUCT_LABEL_FORMATS.items():
        cr.execute(
            "UPDATE stock_picking_type SET product_label_format = %s WHERE product_label_format = %s", (new, old)
        )
        if cr.rowcount:
            _logger.info("UPGRADE20 picking type label format %s -> %s on %s rows", old, new, cr.rowcount)
