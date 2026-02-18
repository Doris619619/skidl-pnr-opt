# -*- coding: utf-8 -*-

# The MIT License (MIT) - Copyright (c) Dave Vandenbout.

"""
Calculate bounding boxes for part symbols and hierarchical sheets.
"""

from skidl.geometry import (
    BBox,
    Point,
    Vector,
    tx_rot_0,
    tx_rot_90,
    tx_rot_180,
    tx_rot_270,
)
from skidl.utilities import export_to_all
from .constants import HIER_TERM_SIZE, PIN_LABEL_FONT_SIZE


def _calc_pin_bbox(part, pin, **options):
    """Calculate bounding box for a pin including its label."""

    label_offset = 20  # mils

    bbox = BBox()
    pt = Point(pin.x, pin.y)
    bbox.add(pt)

    # Add space around the pin for label and margins.
    margin = Point(label_offset + 40, label_offset + 20)
    bbox.add(pt - margin)
    bbox.add(pt + margin)

    return bbox


@export_to_all
def calc_symbol_bbox(part, **options):
    """Return the bounding box of the part symbol.

    Uses pin-based bbox calculation for KiCad 6+.

    Args:
        part: Part object for which a bounding box will be created.
        options (dict): Various options to control bounding box calculation.

    Returns:
        List of BBoxes: [overall_bbox, unit1_bbox, unit2_bbox, ...].
    """

    bboxes = [BBox()]  # Overall bbox at index 0

    for unit_num, unit in part.unit.items():
        unit.bbox = BBox()
        for pin in unit.pins:
            pin_bbox = _calc_pin_bbox(unit, pin, **options)
            unit.bbox.add(pin_bbox)
        bboxes[0].add(unit.bbox)
        bboxes.append(unit.bbox)

    # If no units, create a default bbox from part pins.
    if not part.unit:
        bbox = BBox()
        for pin in part.pins:
            pin_bbox = _calc_pin_bbox(part, pin, **options)
            bbox.add(pin_bbox)
        part.bbox = bbox
        bboxes[0] = bbox
        bboxes.append(bbox)

    return bboxes


@export_to_all
def calc_hier_label_bbox(label, dir):
    """Calculate the bounding box for a hierarchical label.

    Args:
        label (str): String for the label.
        dir (str): Orientation ("U", "D", "L", "R").

    Returns:
        BBox: Bounding box for the label and hierarchical terminal.
    """

    lbl_tx = {
        "U": tx_rot_90,
        "D": tx_rot_270,
        "L": tx_rot_180,
        "R": tx_rot_0,
    }

    lbl_len = len(label) * PIN_LABEL_FONT_SIZE + HIER_TERM_SIZE
    lbl_hgt = max(PIN_LABEL_FONT_SIZE, HIER_TERM_SIZE)

    bbox = BBox(Point(0, lbl_hgt / 2), Point(-lbl_len, -lbl_hgt / 2))
    bbox *= lbl_tx[dir]

    return bbox
