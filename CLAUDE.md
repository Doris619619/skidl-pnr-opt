# SKiDL — Auto-Stub Schematic Generation

## Overview

This branch adds `auto_stub` mode to `generate_schematic()` for reliable KiCad 9 schematic output, even for large/complex circuits. It also fixes several KiCad 9 S-expression format issues.

See `tests/examples/schematics/esp32_audio_board.py` for a full working example.

## Auto-Stub Feature

Opt-in via `generate_schematic(auto_stub=True)`. Handles circuits that would otherwise fail routing:

1. **Pre-generation heuristics** — power nets and high-fanout nets become global labels
2. **Selective routing** — post-placement, nets that are too complex or too spread out get stubbed
3. **Row-based placer** — O(n) BFS placement for groups >20 parts
4. **Power symbol injection** — GND, VCC, +3V3, etc. emit proper KiCad `power:` symbols
5. **ERC correction loop** — runs `kicad-cli sch erc`, stubs failing nets, regenerates

### Options

```python
generate_schematic(
    auto_stub=True,                    # Enable auto-stubbing
    auto_stub_fanout=3,                # Stub nets with more pins than this
    auto_stub_max_wire_pins=3,         # Max pins for wire routing (post-placement)
    auto_stub_max_wire_dist=2000,      # Max manhattan distance for wires (mils)
    erc_max_iterations=8,              # Max ERC correction passes
    auto_stub_fallback="labels",       # "labels" | "raise" | "warn"
)
```

### Best Practice: Use @subcircuit

Group related parts into subcircuits. Each becomes a hierarchical sheet with independently routed connections — produces significantly more wires vs a flat circuit.

```python
@subcircuit
def power_supply(vin, vout, gnd):
    ldo = Part("Regulator_Linear", "AP2112K-3.3")
    ldo[1] += vin; ldo[2] += gnd; ldo[3] += vin; ldo[5] += vout
    # ... decoupling caps ...

@subcircuit
def audio_amp(vbat, vcc, gnd, bclk, lrclk, din):
    amp = Part("Audio", "MAX98357A")
    # ... amp circuit ...

# Top level: define nets, instantiate subcircuits
vcc = Net("VCC"); vcc.drive = POWER
gnd = Net("GND"); gnd.drive = POWER

power_supply(vbat, vcc, gnd)
audio_amp(vbat, vcc, gnd, bclk, lrclk, din)

generate_schematic(auto_stub=True)
```

## File Map

| File | Purpose |
|------|---------|
| `src/skidl/tools/kicad9/gen_schematic.py` | Auto-stub orchestration, selective routing, ERC loop |
| `src/skidl/tools/kicad9/sexp_schematic.py` | S-expression writer, power symbols, hierarchical labels |
| `src/skidl/schematics/place.py` | Row-based placer, grid block fallback |
| `src/skidl/schematics/sch_node.py` | Boundary net detection for hierarchy |
| `src/skidl/tools/inject_labels.py` | Label injection infrastructure |
| `tests/unit_tests/ai_tests/test_auto_stub.py` | 66 tests covering all features |
| `tests/examples/schematics/esp32_audio_board.py` | Full working example |

## Testing

```bash
# Set your KiCad symbol library path
export KICAD9_SYMBOL_DIR=/usr/share/kicad/symbols

# Auto-stub tests
python -m pytest tests/unit_tests/ai_tests/test_auto_stub.py -v

# Full test suite
python -m pytest tests/unit_tests/ai_tests/ -v

# Run the example
python tests/examples/schematics/esp32_audio_board.py
```

## Internals Cheat Sheet

- `net.valid` is a property (not `is_valid()`)
- `net._stub` is the backing field; `net.stub` propagates to pins
- `Part.__init__` defaults to `default_circuit` — pass `circuit=` explicitly for named circuits
- `NetTerminal` is a specialized Part with one pin, used for net labels
- `finalize_parts_and_nets()` must be called after every place/route attempt
- Row-based placer activates for groups >20 parts (`_ROW_PLACE_THRESHOLD`)
- Power symbols detected from `/usr/share/kicad/symbols/power.kicad_sym` (or `KICAD9_SYMBOL_DIR`)
