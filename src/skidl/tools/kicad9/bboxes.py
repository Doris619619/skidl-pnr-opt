# -*- coding: utf-8 -*-

# The MIT License (MIT) - Copyright (c) Dave Vandenbout.

"""
Calculate bounding boxes for part symbols and hierarchical sheets.
"""

from skidl.geometry import (
    BBox,
    Point,
    Vector,
    Tx,
    tx_rot_0,
    tx_rot_90,
    tx_rot_180,
    tx_rot_270,
)
from skidl.utilities import export_to_all
from .constants import HIER_TERM_SIZE, PIN_LABEL_FONT_SIZE

# Character size fudge factor used in draw_cmd_to_svg.
CHAR_SIZE_FUDGE = 0.6


def _calc_draw_cmd_bbox(draw_cmd):
    """Calculate bounding box for a symbol drawing command.

    Args:
        draw_cmd: A drawing command from part.draw_cmds (list format from KiCad s-expression).

    Returns:
        BBox: Bounding box for the drawing command, or empty BBox if unrecognized type.
    """
    if not draw_cmd or len(draw_cmd) < 2:
        return BBox()

    shape_type = draw_cmd[0].lower()

    # Convert draw_cmd to dict for easier access (similar to draw_cmd_to_dict in gen_svg.py).
    # _draw_cmd_to_dict returns (name, dict) tuple, we need the dict.
    _, shape = _draw_cmd_to_dict(draw_cmd)

    # Identity transformation for local coordinates.
    tx = Tx()

    if shape_type == "polyline":
        # Polyline: list of points.
        pts = shape.get("pts", {}).get("xy", [])
        if pts:
            points = [Point(*pt[0:2]) * tx for pt in pts]
            return BBox(*points)
        return BBox()

    elif shape_type == "circle":
        # Circle: center point and radius.
        center = shape.get("center", [0, 0])
        radius = shape.get("radius", 0)
        ctr = Point(*center[0:2]) * tx
        rad_pt = Point(radius, radius)
        return BBox(ctr + rad_pt, ctr - rad_pt)

    elif shape_type == "rectangle":
        # Rectangle: start and end corners.
        start = shape.get("start", [0, 0])
        end = shape.get("end", [0, 0])
        start_pt = Point(*start[0:2]) * tx
        end_pt = Point(*end[0:2]) * tx
        return BBox(start_pt, end_pt)

    elif shape_type == "arc":
        # Arc: start, mid, and end points.
        start = shape.get("start", [0, 0])
        mid = shape.get("mid", [0, 0])
        end = shape.get("end", [0, 0])
        a = Point(*start[0:2]) * tx
        b = Point(*end[0:2]) * tx
        c = Point(*mid[0:2]) * tx
        return BBox(a, b, c)

    elif shape_type == "text":
        # Text: position and font size.
        at = shape.get("at", [0, 0, 0])
        effects = shape.get("effects", {})
        font = effects.get("font", {"size": [0, 0]})
        size = font.get("size", [0, 0])
        misc = shape.get("misc", "")

        start = Point(*at[0:2])
        rotation = at[2] if len(at) > 2 else 0
        justify = shape.get("justify", "left").lower()

        # Direction vector based on justification and rotation.
        dir_dict = {"right": Point(1, 0), "left": Point(-1, 0), "center": Point(-1, 0)}
        dir = dir_dict.get(justify, Point(-1, 0)) * Tx().rot(rotation)

        char_wid = size[0] * CHAR_SIZE_FUDGE
        char_hgt = size[1] * CHAR_SIZE_FUDGE

        return _text_bbox(misc, start, dir, char_wid, char_hgt)

    elif shape_type == "property":
        # Property (reference/value): similar to text but with different default direction.
        effects = shape.get("effects", {})
        if effects.get("hide", False):
            return BBox()  # Hidden properties have no bbox.

        at = shape.get("at", [0, 0, 0])
        font = effects.get("font", {"size": [0, 0]})
        size = font.get("size", [0, 0])
        misc = shape.get("misc", "")

        # Handle misc as either a string or a list.
        if isinstance(misc, list):
            text = misc[1] if len(misc) > 1 else ""
        else:
            text = misc

        start = Point(*at[0:2])
        rotation = at[2] if len(at) > 2 else 0
        justify = effects.get("justify", "center")
        if isinstance(justify, list):
            justify = justify[0]
        justify = justify.lower() if isinstance(justify, str) else "center"

        # Direction vector: right justify extends left, left extends right.
        dir_dict = {"right": Point(-1, 0), "left": Point(1, 0), "center": Point(-1, 0)}
        dir = dir_dict.get(justify, Point(-1, 0)) * Tx().rot(rotation)

        char_wid = size[0] * CHAR_SIZE_FUDGE
        char_hgt = size[1] * CHAR_SIZE_FUDGE

        return _text_bbox(text, start, dir, char_wid, char_hgt)

    elif shape_type == "pin":
        # Pins: calculate bbox similar to _calc_pin_bbox.
        # Extract position from "at" field.
        at = shape.get("at", [0, 0, 0])
        pt = Point(*at[0:2])

        # Add space around the pin for label and margins (same as _calc_pin_bbox).
        label_offset = 20  # mils
        margin = Point(label_offset + 40, label_offset + 20)
        bbox = BBox()
        bbox.add(pt)
        bbox.add(pt - margin)
        bbox.add(pt + margin)
        return bbox

    # Unknown shape type - return empty bbox.
    return BBox()


def _text_bbox(text, start, dir, char_wid, char_hgt):
    """Calculate bounding box for text.

    Args:
        text: String text.
        start: Point where text starts.
        dir: Direction vector for text orientation.
        char_wid: Width of a single character.
        char_hgt: Height of a single character.

    Returns:
        BBox: Bounding box for the text.
    """
    if not text:
        return BBox()

    char_wid *= CHAR_SIZE_FUDGE
    char_hgt *= CHAR_SIZE_FUDGE
    ortho_dir = dir * Tx().rot(90)

    p1 = start - ortho_dir * char_hgt / 2
    p2 = start + ortho_dir * char_hgt / 2
    p3 = p1 + dir * char_wid * len(text)
    p4 = p2 + dir * char_wid * len(text)

    return BBox(p1, p2, p3, p4)


def _draw_cmd_to_dict(symbol):
    """Convert a symbol drawing command list into a dictionary for easier access.

    This is a simplified version of draw_cmd_to_dict from gen_svg.py.

    Args:
        symbol: A drawing command list from KiCad s-expression.

    Returns:
        dict: Dictionary representation of the drawing command.
    """
    d = {}
    name = symbol[0]
    items = symbol[1:]

    is_named_present = False
    item_names = []

    for item in items:
        if isinstance(item, list):
            result = _draw_cmd_to_dict(item)
            if isinstance(result, tuple):
                # Result is a (name, dict) tuple from a nested command
                item_name, item_dict = result
                is_named_present = True
            else:
                # Result is just a value (no nested commands)
                item_name = "misc"
                item_dict = result
        else:
            item_name = "misc"
            item_dict = item

        if item_name not in item_names:
            item_names.append(item_name)
        if item_name not in d:
            d[item_name] = [item_dict]
        else:
            d[item_name].append(item_dict)

    # If a list has only one item, remove it from the list.
    for item_name in item_names:
        if len(d[item_name]) == 1:
            d[item_name] = d[item_name][0]

    if not is_named_present:
        d = d["misc"]

    return name, d


@export_to_all
def calc_symbol_bbox(part, **options):
    """Return the bounding box of the part symbol.

    Calculates bounding box from the symbol's draw_cmds including pins,
    graphical objects (polyline, circle, rectangle, arc), and text.

    Args:
        part: Part object for which a bounding box will be created.
        options (dict): Various options to control bounding box calculation.

    Returns:
        List of BBoxes: [overall_bbox, unit1_bbox, unit2_bbox, ...].
    """

    bboxes = [BBox()]  # Overall bbox at index 0

    # Get draw_cmds if available (contains graphical objects like rectangles, circles, text, etc.).
    draw_cmds = getattr(part, "draw_cmds", {})

    for unit_num, unit in part.unit.items():
        unit.bbox = BBox()

        # Add bounding boxes for pins from draw_cmds.
        # Also check global draw_cmds (unit 0) which may contain pins.
        for cmd_key in [unit_num, 0]:
            for cmd in draw_cmds.get(cmd_key, []):
                if cmd and len(cmd) > 0 and cmd[0].lower() == "pin":
                    pin_bbox = _calc_draw_cmd_bbox(cmd)
                    unit.bbox.add(pin_bbox)

        # Add bounding boxes for graphical/text objects in this unit.
        for cmd_key in [unit_num, 0]:
            for cmd in draw_cmds.get(cmd_key, []):
                if not cmd or len(cmd) == 0:
                    continue
                cmd_type = cmd[0].lower()
                if cmd_type != "pin":
                    cmd_bbox = _calc_draw_cmd_bbox(cmd)
                    unit.bbox.add(cmd_bbox)

        bboxes[0].add(unit.bbox)
        bboxes.append(unit.bbox)

    # If no units, create a default bbox from part pins and draw_cmds.
    if not part.unit:
        bbox = BBox()

        # Add bounding boxes for all draw commands (pins, graphics, text).
        # Check both unit 1 and unit 0 draw_cmds.
        for unit_key in [1, 0]:
            for cmd in draw_cmds.get(unit_key, []):
                cmd_bbox = _calc_draw_cmd_bbox(cmd)
                bbox.add(cmd_bbox)

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
