# -*- coding: utf-8 -*-

# The MIT License (MIT) - Copyright (c) Dave Vandenbout.

"""
Generate a KiCad 9 schematic from a Circuit object.

Thin wrapper around the shared sexp_schematic module.
Uses SKiDL's placement and routing infrastructure.
"""

import os
from collections import Counter

from skidl.geometry import BBox, Point, Tx, Vector
from skidl.scriptinfo import get_script_name
from skidl.schematics.net_terminal import NetTerminal
from skidl.tools.kicad9.sexp_schematic import write_top_schematic
from skidl.utilities import export_to_all, rmv_attr
from .bboxes import calc_symbol_bbox, calc_hier_label_bbox

__all__ = []


def preprocess_circuit(circuit, **options):
    """Add stuff to parts & nets for doing placement and routing of schematics."""

    def units(part):
        if len(part.unit) == 0:
            return [part]
        else:
            return part.unit.values()

    def initialize(part):
        """Initialize part or its part units."""

        pin_limit = options.get("orientation_pin_limit", 44)

        # KiCad 6+ stores pin orientation as integer degrees; normalize to string.
        deg_to_orient = {0: "R", 90: "U", 180: "L", 270: "D"}

        for part_unit in units(part):
            part_unit.tx = Tx.from_symtx(getattr(part_unit, "symtx", ""))

            num_pins = len(part_unit.pins)
            part_unit.orientation_locked = getattr(part_unit, "symtx", False) or not (
                1 < num_pins <= pin_limit
            )

            part_unit.grab_pins()

            for pin in part_unit:
                # Normalize pin orientation from integer degrees to string direction.
                if isinstance(pin.orientation, int):
                    pin.orientation = deg_to_orient.get(pin.orientation % 360, "R")
                pin.pt = Point(pin.x, pin.y)
                pin.routed = False

    def rotate_power_pins(part):
        """Rotate a part based on the direction of its power pins."""

        if not getattr(part, "symtx", ""):
            return

        def is_pwr(net_name):
            return net_name.startswith("+")

        def is_gnd(net_name):
            return "gnd" in net_name.lower()

        dont_rotate_pin_cnt = options.get("dont_rotate_pin_count", 10000)

        for part_unit in units(part):
            if len(part_unit) > dont_rotate_pin_cnt:
                return

            rotation_tally = Counter()
            for pin in part_unit:
                net_name = getattr(pin.net, "name", "").lower()
                if is_gnd(net_name):
                    if pin.orientation == "U":
                        rotation_tally[0] += 1
                    if pin.orientation == "D":
                        rotation_tally[180] += 1
                    if pin.orientation == "L":
                        rotation_tally[90] += 1
                    if pin.orientation == "R":
                        rotation_tally[270] += 1
                elif is_pwr(net_name):
                    if pin.orientation == "D":
                        rotation_tally[0] += 1
                    if pin.orientation == "U":
                        rotation_tally[180] += 1
                    if pin.orientation == "L":
                        rotation_tally[270] += 1
                    if pin.orientation == "R":
                        rotation_tally[90] += 1

            try:
                rotation = rotation_tally.most_common()[0][0]
            except IndexError:
                pass
            else:
                tx_cw_90 = Tx(a=0, b=-1, c=1, d=0)
                for _ in range(int(round(rotation / 90))):
                    part_unit.tx = part_unit.tx * tx_cw_90

    def calc_part_bbox(part):
        """Calculate the labeled bounding boxes and store it in the part."""

        bare_bboxes = calc_symbol_bbox(part)[1:]

        for part_unit, bare_bbox in zip(units(part), bare_bboxes):
            resize_wh = Vector(0, 0)
            if bare_bbox.w < 100:
                resize_wh.x = (100 - bare_bbox.w) / 2
            if bare_bbox.h < 100:
                resize_wh.y = (100 - bare_bbox.h) / 2
            bare_bbox = bare_bbox.resize(resize_wh)

            part_unit.lbl_bbox = BBox()
            part_unit.lbl_bbox.add(bare_bbox)
            for pin in part_unit:
                if pin.stub:
                    hlbl_bbox = calc_hier_label_bbox(pin.net.name, pin.orientation)
                    hlbl_bbox *= Tx().move(pin.pt)
                    part_unit.lbl_bbox.add(hlbl_bbox)

            part_unit.bbox = part_unit.lbl_bbox

    for part in circuit.parts:
        initialize(part)
        rotate_power_pins(part)
        calc_part_bbox(part)


def finalize_parts_and_nets(circuit, **options):
    """Restore parts and nets after place & route is done."""

    net_terminals = (p for p in circuit.parts if isinstance(p, NetTerminal))
    circuit.rmv_parts(*net_terminals)

    for part in circuit.parts:
        part.grab_pins()

    rmv_attr(circuit.parts, ("force", "bbox", "lbl_bbox", "tx"))


@export_to_all
def gen_schematic(
    circuit,
    filepath=".",
    top_name=get_script_name(),
    title="SKiDL-Generated Schematic",
    flatness=0.0,
    retries=2,
    **options
):
    """Create a KiCad 8 schematic file from a Circuit object.

    Args:
        circuit (Circuit): The Circuit object that will have a schematic generated for it.
        filepath (str, optional): The directory where the schematic files are placed. Defaults to ".".
        top_name (str, optional): The name for the top of the circuit hierarchy. Defaults to get_script_name().
        title (str, optional): The title of the schematic. Defaults to "SKiDL-Generated Schematic".
        flatness (float, optional): Determines how much the hierarchy is flattened in the schematic. Defaults to 0.0 (completely hierarchical).
        retries (int, optional): Number of times to re-try if routing fails. Defaults to 2.
        options (dict, optional): Dict of options and values, usually for drawing/debugging.
    """

    from skidl import KICAD8
    from skidl.schematics.place import PlacementFailure
    from skidl.schematics.route import RoutingFailure
    from skidl.tools import tool_modules
    from skidl.schematics.sch_node import SchNode
    from skidl.logger import active_logger

    # Part placement options that should always be turned on.
    options["use_push_pull"] = True
    options["rotate_parts"] = True
    options["pt_to_pt_mult"] = 5
    options["pin_normalize"] = True

    expansion_factor = 1.0
    failure_type = None

    for attempt in range(retries):
        preprocess_circuit(circuit, **options)

        node = SchNode(circuit, tool_modules[KICAD8], filepath, top_name, title, flatness)

        try:
            node.place(expansion_factor=expansion_factor, **options)
            node.route(**options)

        except PlacementFailure as e:
            finalize_parts_and_nets(circuit, **options)
            failure_type = e
            active_logger.warning(f"Placement failed on attempt {attempt + 1}/{retries}: {e}")
            continue

        except RoutingFailure as e:
            finalize_parts_and_nets(circuit, **options)
            expansion_factor *= 1.5
            failure_type = e
            active_logger.warning(
                f"Routing failed on attempt {attempt + 1}/{retries}, expanding area by 1.5x: {e}"
            )
            continue

        # Generate S-expression schematic using shared module.
        # KiCad 8/9 use version 20230409.
        output_file = write_top_schematic(
            circuit, node, filepath, top_name, title, version=20230409
        )

        active_logger.info(f"Schematic written to {output_file}")

        finalize_parts_and_nets(circuit, **options)
        return

    finalize_parts_and_nets(circuit, **options)

    if failure_type:
        raise failure_type
    else:
        raise RuntimeError("Schematic generation failed for unknown reasons")
