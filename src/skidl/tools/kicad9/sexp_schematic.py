# -*- coding: utf-8 -*-

# The MIT License (MIT) - Copyright (c) Dave Vandenbout.

"""
Shared S-expression schematic generation for KiCad 6/8/9.

Converts placed+routed SchNode trees into .kicad_sch files.
Used by kicad6, kicad8, and kicad9 gen_schematic thin wrappers.

Sources:
  - part_to_sexp / wire_to_sexp: upstream sexp_schematics branch (devbisme)
  - Hierarchy / custom fields / lib_symbols: feature/kicad8-gen-schematic (PR #281)
  - Net label logic: feature/inject-net-labels (PR #280)
  - Original kicad5 hierarchy walker: node_to_eeschema (kicad5/gen_schematic.py)
  - Credit: cyberhuman (PR #270) for initial KiCad 8 schematic work
"""

import copy
import datetime
import os
import uuid
from collections import OrderedDict

from simp_sexp import Sexp

from skidl.geometry import Point, Tx
from skidl.pckg_info import __version__
from skidl.schematics.net_terminal import NetTerminal
from skidl.utilities import export_to_all

# UUID namespace — same as gen_netlist.py so UUIDs are cross-referenceable.
_NAMESPACE_UUID = uuid.UUID("7026fcc6-e1a0-409e-aaf4-6a17ea82654f")


def _gen_uuid(name=""):
    """Generate a deterministic UUID from *name*, or a random one if empty."""
    if not name:
        return str(uuid.uuid4())
    return str(uuid.uuid5(_NAMESPACE_UUID, name))


# ---------------------------------------------------------------------------
# Paper sizes
# ---------------------------------------------------------------------------

A_SIZES = OrderedDict(
    [
        ("A4", (297, 210)),
        ("A3", (420, 297)),
        ("A2", (594, 420)),
        ("A1", (841, 594)),
        ("A0", (1189, 841)),
    ]
)


def _pick_paper_size(bbox):
    """Choose the smallest A-size paper that fits *bbox* (in mils)."""
    import math

    w = abs(bbox.w) if bbox.w and not math.isinf(bbox.w) else 0
    h = abs(bbox.h) if bbox.h and not math.isinf(bbox.h) else 0

    # Convert bbox dimensions from mils to mm.
    w_mm = w * 0.0254 if w else 0
    h_mm = h * 0.0254 if h else 0

    for name, (pw, ph) in A_SIZES.items():
        if w_mm <= pw and h_mm <= ph:
            return name
    return "A0"


# ---------------------------------------------------------------------------
# Part → S-expression
# ---------------------------------------------------------------------------


def part_to_sexp(part, tx=Tx()):
    """Create S-expression for a symbol instance.

    Applies part transform and sheet transform (Y-flip is in sheet_tx).

    Args:
        part: SKiDL Part object (placed).
        tx: Sheet-level transformation matrix.

    Returns:
        Sexp: Symbol S-expression.
    """
    part_tx = getattr(part, "tx", Tx())
    tx = part_tx * tx
    origin = tx.origin.round()
    unit_num = getattr(part, "num", 1)

    lib_name = (
        os.path.splitext(part.lib.filename)[0]
        if hasattr(part.lib, "filename") and part.lib.filename
        else "Device"
    )
    part_name = part.name or "Unknown"
    lib_id = f"{lib_name}:{part_name}"

    symbol = Sexp(
        [
            "symbol",
            ["lib_id", lib_id],
            ["at", origin.x, origin.y, 0],
            ["unit", unit_num],
            ["exclude_from_sim", "no"],
            ["in_bom", "yes"],
            ["on_board", "yes"],
            ["dnp", "no"],
            ["fields_autoplaced", "yes"],
            ["uuid", _gen_uuid(part.hiername)],
        ]
    )

    # Reference
    symbol.append(
        Sexp(
            [
                "property",
                "Reference",
                part.ref,
                ["at", origin.x, origin.y - 2.54, 0],
                ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left"]],
            ]
        )
    )

    # Value
    symbol.append(
        Sexp(
            [
                "property",
                "Value",
                str(part.value),
                ["at", origin.x, origin.y + 2.54, 0],
                ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left"]],
            ]
        )
    )

    # Footprint
    symbol.append(
        Sexp(
            [
                "property",
                "Footprint",
                getattr(part, "footprint", ""),
                ["at", origin.x, origin.y, 0],
                ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]],
            ]
        )
    )

    # Datasheet
    symbol.append(
        Sexp(
            [
                "property",
                "Datasheet",
                getattr(part, "datasheet", "~") or "~",
                ["at", origin.x, origin.y, 0],
                ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]],
            ]
        )
    )

    # Description
    symbol.append(
        Sexp(
            [
                "property",
                "Description",
                getattr(part, "description", "") or "",
                ["at", origin.x, origin.y, 0],
                ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]],
            ]
        )
    )

    # Custom fields from part.fields dict.
    y_offset = 5.08
    if hasattr(part, "fields") and part.fields:
        for field_name, field_value in part.fields.items():
            if field_name.lower() in (
                "reference",
                "value",
                "footprint",
                "datasheet",
                "description",
            ):
                continue
            if field_value and str(field_value).strip():
                symbol.append(
                    Sexp(
                        [
                            "property",
                            field_name,
                            str(field_value),
                            ["at", origin.x, origin.y + y_offset, 0],
                            [
                                "effects",
                                ["font", ["size", 1.27, 1.27]],
                                ["hide", "yes"],
                            ],
                        ]
                    )
                )
                y_offset += 1.27

    # Instances section (required by KiCad 8/9 for correct reference display).
    symbol.append(
        Sexp(
            [
                "instances",
                [
                    "project",
                    "SKiDL-Generated",
                    [
                        "path",
                        f"/{_gen_uuid('root_schematic')}",
                        ["reference", part.ref],
                        ["unit", unit_num],
                    ],
                ],
            ]
        )
    )

    return symbol


# ---------------------------------------------------------------------------
# Library symbol definition
# ---------------------------------------------------------------------------


def part_to_lib_symbol_definition(part):
    """Extract library symbol definition from a part's draw_cmds.

    Args:
        part: SKiDL Part object.

    Returns:
        list: Nested list for the lib_symbols section.
    """
    lib_name = (
        os.path.splitext(part.lib.filename)[0]
        if hasattr(part.lib, "filename") and part.lib.filename
        else "Device"
    )
    part_name = part.name or "Unknown"
    lib_id = f"{lib_name}:{part_name}"

    symbol_def = [
        "symbol",
        lib_id,
        ["pin_numbers", ["hide", "yes"]],
        ["pin_names", ["offset", 0]],
        ["exclude_from_sim", "no"],
        ["in_bom", "yes"],
        ["on_board", "yes"],
    ]

    # Standard properties.
    symbol_def.extend(
        [
            [
                "property",
                "Reference",
                part.ref_prefix or "U",
                ["at", 2.032, 0, 90],
                ["effects", ["font", ["size", 1.27, 1.27]]],
            ],
            [
                "property",
                "Value",
                part_name,
                ["at", 0, 0, 90],
                ["effects", ["font", ["size", 1.27, 1.27]]],
            ],
            [
                "property",
                "Footprint",
                "",
                ["at", 0, 0, 0],
                ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]],
            ],
            [
                "property",
                "Datasheet",
                getattr(part, "datasheet", "~") or "~",
                ["at", 0, 0, 0],
                ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]],
            ],
        ]
    )

    if hasattr(part, "description") and part.description:
        symbol_def.append(
            [
                "property",
                "Description",
                part.description,
                ["at", 0, 0, 0],
                ["effects", ["font", ["size", 1.27, 1.27]], ["hide", "yes"]],
            ]
        )

    # Process draw_cmds into sub-symbols.
    if hasattr(part, "draw_cmds") and part.draw_cmds:
        # Common graphics (unit 0).
        if 0 in part.draw_cmds:
            graphics = [
                copy.deepcopy(cmd) for cmd in part.draw_cmds[0] if cmd[0] != "pin"
            ]
            if graphics:
                symbol_def.append(["symbol", f"{part_name}_0_1"] + graphics)

        # Per-unit graphics and pins.
        for unit_num, draw_cmds in part.draw_cmds.items():
            if unit_num == 0:
                continue
            pin_cmds = [copy.deepcopy(cmd) for cmd in draw_cmds if cmd[0] == "pin"]
            graphics = [
                copy.deepcopy(cmd)
                for cmd in draw_cmds
                if cmd[0] not in ("pin", "property")
            ]
            if pin_cmds or graphics:
                unit_sym = ["symbol", f"{part_name}_{unit_num}_{unit_num}"]
                unit_sym.extend(graphics)
                unit_sym.extend(pin_cmds)
                symbol_def.append(unit_sym)

    symbol_def.append(["embedded_fonts", "no"])

    return symbol_def


# ---------------------------------------------------------------------------
# Wires, junctions, net labels
# ---------------------------------------------------------------------------


def wire_to_sexp(net, wire, tx=Tx()):
    """Create S-expression for wire segments.

    Args:
        net: Net associated with the wire.
        wire: List of Segments.
        tx: Transformation matrix.

    Returns:
        list[Sexp]: Wire S-expression objects.
    """
    wires = []
    for segment in wire:
        w = (segment * tx).round()
        wires.append(
            Sexp(
                [
                    "wire",
                    ["pts", ["xy", w.p1.x, w.p1.y], ["xy", w.p2.x, w.p2.y]],
                    ["stroke", ["width", 0], ["type", "default"]],
                    ["uuid", _gen_uuid(f"wire:{net.name}:{w.p1.x}:{w.p1.y}")],
                ]
            )
        )
    return wires


def junction_to_sexp(net, junctions, tx=Tx()):
    """Create S-expression for junction points.

    Args:
        net: Net associated with the junctions.
        junctions: List of junction Points.
        tx: Transformation matrix.

    Returns:
        list[Sexp]: Junction S-expression objects.
    """
    result = []
    for junction in junctions:
        pt = (junction * tx).round()
        result.append(
            Sexp(
                [
                    "junction",
                    ["at", pt.x, pt.y],
                    ["diameter", 0],
                    ["color", 0, 0, 0, 0],
                    ["uuid", _gen_uuid(f"junction:{pt.x}:{pt.y}")],
                ]
            )
        )
    return result


def net_label_to_sexp(pin, tx=Tx()):
    """Create S-expression for a net label at a pin stub.

    Generates a local label if all connected pins share a common hierarchy
    ancestor, otherwise generates a global_label.

    Args:
        pin: Pin with net connection.
        tx: Transformation matrix.

    Returns:
        Sexp or None: Label S-expression, or None if no label needed.
    """
    if not pin.stub or not pin.is_connected():
        return None

    # Determine label type based on hierarchy span.
    label_type = "label"
    pin_hier = pin.part.hiertuple
    for pn in pin.net.pins:
        pn_hier = pn.part.hiertuple
        if pin_hier[: len(pn_hier)] == pn_hier:
            continue
        if pn_hier[: len(pin_hier)] == pin_hier:
            continue
        label_type = "global_label"
        break

    # Position at pin location (Y-flip is already in sheet_tx).
    part_tx = getattr(pin.part, "tx", Tx())
    tx = part_tx * tx
    pin_pt = getattr(pin, "pt", Point(pin.x, pin.y))
    pt = (pin_pt * tx).round()

    # Map pin orientation to angle (degrees).
    orient_map = {"R": 0, "D": 90, "L": 180, "U": 270}
    angle = orient_map.get(pin.orientation, 0)

    label = Sexp(
        [
            label_type,
            pin.net.name,
            ["at", pt.x, pt.y, angle],
            ["fields_autoplaced", "yes"],
            ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left"]],
            ["uuid", _gen_uuid(f"label:{pin.net.name}:{pt.x}:{pt.y}")],
        ]
    )

    return label


# ---------------------------------------------------------------------------
# Title block
# ---------------------------------------------------------------------------


def create_title_block_sexp(title):
    """Create a title block S-expression."""
    return [
        "title_block",
        ["title", title],
        ["date", datetime.date.today().isoformat()],
        ["company", ""],
        ["comment", 1, "Generated with SKiDL"],
        ["comment", 2, ""],
        ["comment", 3, ""],
        ["comment", 4, ""],
    ]


# ---------------------------------------------------------------------------
# Hierarchical sheet reference
# ---------------------------------------------------------------------------


def create_hierarchical_sheet_sexp(node, sheet_tx):
    """Create a hierarchical sheet S-expression for insertion into a parent sheet.

    Args:
        node: SchNode for the child sheet.
        sheet_tx: Transformation matrix of the parent sheet.

    Returns:
        Sexp: Sheet S-expression.
    """
    bbox = (node.bbox * node.tx * sheet_tx).round()
    sheet_uuid = _gen_uuid(f"sheet:{node.sheet_filename}")

    sheet = Sexp(
        [
            "sheet",
            ["at", bbox.ll.x, bbox.ll.y],
            ["size", bbox.w, bbox.h],
            ["exclude_from_sim", "no"],
            ["in_bom", "yes"],
            ["on_board", "yes"],
            ["dnp", "no"],
            ["fields_autoplaced", "yes"],
            ["stroke", ["width", 0.1524], ["type", "solid"]],
            ["fill", ["color", 0, 0, 0, 0.0]],
            ["uuid", sheet_uuid],
            [
                "property",
                "Sheetname",
                node.name,
                ["at", bbox.ll.x, bbox.ll.y - 0.7116, 0],
                [
                    "effects",
                    ["font", ["size", 1.27, 1.27]],
                    ["justify", "left", "bottom"],
                ],
            ],
            [
                "property",
                "Sheetfile",
                node.sheet_filename,
                ["at", bbox.ll.x, bbox.ll.y + bbox.h + 0.5846, 0],
                ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left", "top"]],
            ],
        ]
    )

    return sheet


# ---------------------------------------------------------------------------
# Sheet-level transform calculation (mirrors kicad5 calc_sheet_tx)
# ---------------------------------------------------------------------------

MILS_TO_MM = 0.0254


def _calc_sheet_tx(bbox):
    """Calculate transformation matrix for placing circuitry in a sheet.

    Mirrors the kicad5 calc_sheet_tx pattern:
      1. Y-flip via d=-1 (placement engine is Y-up, KiCad is Y-down)
      2. Mils-to-mm conversion via a/d scaling (KiCad 9 uses mm)
      3. Center content on the chosen paper size

    The Y-flip is built into this transform so callers must NOT apply
    tx_flip_y separately (that would double-flip and cancel it out).
    """
    paper = _pick_paper_size(bbox)
    pw, ph = A_SIZES[paper]  # mm

    # Apply Y-flip + mils→mm in one transform, then center on page.
    page_bbox = bbox * Tx(a=MILS_TO_MM, d=-MILS_TO_MM)
    page_ctr = Point(pw / 2, ph / 2)
    content_ctr = Point(
        (page_bbox.ll.x + page_bbox.ur.x) / 2,
        (page_bbox.ll.y + page_bbox.ur.y) / 2,
    )
    move = page_ctr - content_ctr
    tx = Tx(a=MILS_TO_MM, d=-MILS_TO_MM).move(move)

    return tx, paper


# ---------------------------------------------------------------------------
# Recursive hierarchy walker — node_to_sexp_schematic
# ---------------------------------------------------------------------------


def _fix_sheet_filename(node):
    """Ensure node.sheet_filename uses .kicad_sch extension (SchNode defaults to .sch)."""
    if node.sheet_filename and node.sheet_filename.endswith(".sch"):
        node.sheet_filename = node.sheet_filename[:-4] + ".kicad_sch"


@export_to_all
def node_to_sexp_schematic(node, sheet_tx=Tx(), version=20230409):
    """Convert a SchNode tree to S-expression schematic(s).

    Follows the same recursive pattern as kicad5's node_to_eeschema():
    - Flattened nodes: return elements for inclusion in the parent sheet.
    - Unflattened nodes: write a separate .kicad_sch file and return a
      sheet reference for the parent.

    Args:
        node: SchNode to convert.
        sheet_tx: Parent sheet transformation matrix.
        version: S-expression version number (20240108 for kicad6, 20230409 for kicad8/9).

    Returns:
        list[Sexp]: S-expression elements (parts, wires, labels, or a sheet ref).
    """
    # Fix filename extension for KiCad 6+ S-expression format.
    _fix_sheet_filename(node)

    elements = []

    if node.flattened:
        tx = node.tx * sheet_tx
    else:
        # Unflattened node gets its own sheet.
        flattened_bbox = node.internal_bbox()
        tx, paper = _calc_sheet_tx(flattened_bbox)

    # Recurse into children.
    for child in node.children.values():
        elements.extend(node_to_sexp_schematic(child, tx, version=version))

    # Collect lib_symbols needed for this node's parts.
    lib_symbols = {}
    for part in node.parts:
        if not isinstance(part, NetTerminal):
            lib_id = f"{part.lib.filename}:{part.name}"
            if lib_id not in lib_symbols:
                lib_symbols[lib_id] = part

    # Generate part S-expressions.
    for part in node.parts:
        if isinstance(part, NetTerminal):
            # NetTerminals become net labels.
            label = net_label_to_sexp(part.pins[0], tx=tx)
            if label:
                elements.append(label)
        else:
            elements.append(part_to_sexp(part, tx=tx))

    # Generate wire S-expressions.
    for net, wire in node.wires.items():
        elements.extend(wire_to_sexp(net, wire, tx=tx))

    # Generate junction S-expressions.
    for net, junctions in node.junctions.items():
        elements.extend(junction_to_sexp(net, junctions, tx=tx))

    # Generate net labels for stubbed pins.
    for part in node.parts:
        if isinstance(part, NetTerminal):
            continue
        for pin in part:
            label = net_label_to_sexp(pin, tx=tx)
            if label:
                elements.append(label)

    if node.flattened:
        # Return elements for inclusion in the parent sheet.
        return elements

    # --- Unflattened node: write a separate .kicad_sch file. ---

    # Build lib_symbols section for this sheet.
    lib_symbols_sexp = Sexp(["lib_symbols"])
    for lib_id, part in lib_symbols.items():
        lib_symbols_sexp.append(Sexp(part_to_lib_symbol_definition(part)))

    schematic = Sexp(
        [
            "kicad_sch",
            ["version", version],
            ["generator", "skidl"],
            ["generator_version", __version__],
            ["uuid", _gen_uuid(f"sheet:{node.sheet_filename}")],
            ["paper", paper if not node.flattened else "A3"],
        ]
    )
    schematic.append(Sexp(create_title_block_sexp(node.title)))
    schematic.append(lib_symbols_sexp)

    for elem in elements:
        schematic.append(elem)

    # Write schematic file.
    filepath = os.path.join(node.filepath, node.sheet_filename)
    _write_sexp_schematic(schematic, filepath)

    # Return a hierarchical sheet reference for the parent.
    return [create_hierarchical_sheet_sexp(node, sheet_tx)]


# ---------------------------------------------------------------------------
# Top-level schematic assembly + write
# ---------------------------------------------------------------------------


@export_to_all
def write_top_schematic(circuit, node, filepath, top_name, title, version=20230409):
    """Generate and write the complete schematic from a placed+routed node tree.

    This is the main entry point called by each tool's gen_schematic().

    Args:
        circuit: The Circuit object.
        node: Root SchNode (placed and routed).
        filepath: Output directory.
        top_name: Base filename (without extension).
        title: Schematic title.
        version: S-expression version number.
    """
    top_name = top_name or "schematic"
    _fix_sheet_filename(node)

    # Calculate root sheet transform.
    root_bbox = node.internal_bbox()
    sheet_tx, paper = _calc_sheet_tx(root_bbox)

    elements = []

    # Recurse into children — they write their own files if unflattened.
    for child in node.children.values():
        elements.extend(node_to_sexp_schematic(child, sheet_tx, version=version))

    # Collect lib_symbols for ALL parts in the circuit.
    lib_symbols = {}
    for part in circuit.parts:
        if not isinstance(part, NetTerminal):
            lib_id = f"{part.lib.filename}:{part.name}"
            if lib_id not in lib_symbols:
                lib_symbols[lib_id] = part

    # Generate part S-expressions for root-level parts.
    for part in node.parts:
        if isinstance(part, NetTerminal):
            label = net_label_to_sexp(part.pins[0], tx=sheet_tx)
            if label:
                elements.append(label)
        else:
            elements.append(part_to_sexp(part, tx=sheet_tx))

    # Generate wire S-expressions.
    for net, wire in node.wires.items():
        elements.extend(wire_to_sexp(net, wire, tx=sheet_tx))

    # Generate junction S-expressions.
    for net, junctions in node.junctions.items():
        elements.extend(junction_to_sexp(net, junctions, tx=sheet_tx))

    # Generate net labels for stubbed pins.
    for part in node.parts:
        if isinstance(part, NetTerminal):
            continue
        for pin in part:
            label = net_label_to_sexp(pin, tx=sheet_tx)
            if label:
                elements.append(label)

    # Build lib_symbols section.
    lib_symbols_sexp = Sexp(["lib_symbols"])
    for lib_id, part in lib_symbols.items():
        lib_symbols_sexp.append(Sexp(part_to_lib_symbol_definition(part)))

    root_uuid = _gen_uuid("root_schematic")

    schematic = Sexp(
        [
            "kicad_sch",
            ["version", version],
            ["generator", "skidl"],
            ["generator_version", __version__],
            ["uuid", root_uuid],
            ["paper", paper],
        ]
    )
    schematic.append(Sexp(create_title_block_sexp(title)))
    schematic.append(lib_symbols_sexp)

    for elem in elements:
        schematic.append(elem)

    # Write root schematic.
    output_file = os.path.join(filepath, f"{top_name}.kicad_sch")
    os.makedirs(filepath, exist_ok=True)
    _write_sexp_schematic(schematic, output_file)

    # Optional: validate with kicad-cli if available.
    _validate_with_kicad_cli(output_file)

    return output_file


# ---------------------------------------------------------------------------
# Optional KiCad CLI validation
# ---------------------------------------------------------------------------


def _validate_with_kicad_cli(filepath):
    """Run kicad-cli ERC on generated schematic if available."""
    import shutil
    import subprocess

    kicad_cli = shutil.which("kicad-cli")
    if not kicad_cli:
        return  # Silent skip if not installed.
    try:
        result = subprocess.run(
            [kicad_cli, "sch", "erc", "--exit-code-violations", filepath],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            from skidl.logger import active_logger

            active_logger.warning(
                f"KiCad ERC found issues in {filepath}:\n{result.stderr}"
            )
    except (subprocess.TimeoutExpired, OSError):
        pass  # Don't fail generation if CLI has issues.


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------


def _write_sexp_schematic(schematic, filepath):
    """Write an Sexp schematic object to a file with proper quoting.

    Args:
        schematic: Sexp object.
        filepath: Output file path.
    """

    def need_quote(x):
        tag = x[0]
        return tag in (
            "title",
            "date",
            "company",
            "comment",
            "path",
            "project",
            "property",
            "name",
            "number",
            "lib_id",
            "reference",
        )

    def need_quote_alternate(x):
        return x[0] == "alternate"

    schematic.add_quotes(need_quote)
    schematic.add_quotes(need_quote_alternate, stop_idx=2)

    # Fix inner quotes that add_quotes doesn't escape.
    _escape_inner_quotes(schematic)

    with open(filepath, "w") as f:
        f.write(schematic.to_str())


def _escape_inner_quotes(sexp):
    """Escape double quotes inside already-quoted S-expression strings.

    simp_sexp's add_quotes() wraps strings in double quotes but doesn't
    escape inner quotes, producing invalid output like:
        (property "Description" "label with name "GND" , ground")
    This walks the tree and fixes them to:
        (property "Description" "label with name \\"GND\\" , ground")
    """
    for i, item in enumerate(sexp):
        if isinstance(item, list):
            _escape_inner_quotes(item)
        elif isinstance(item, str) and item.startswith('"') and item.endswith('"'):
            inner = item[1:-1]
            if '"' in inner:
                sexp[i] = '"' + inner.replace('"', '\\"') + '"'
