# -*- coding: utf-8 -*-

# The MIT License (MIT) - Copyright (c) Dave Vandenbout.

"""
Generate a KiCad 9 schematic from a Circuit object.

KiCad 9 uses the same S-expression format as KiCad 8,
so this module re-exports from kicad8.
"""

from skidl.tools.kicad8.gen_schematic import gen_schematic  # noqa: F401
