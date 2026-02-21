# SKiDL — Lachlan's Fork

## What This Fork Does

This is a fork of [devbisme/skidl](https://github.com/devbisme/skidl) with KiCad 9 schematic generation fixes and the auto-stub + ERC correction loop feature. Branch: `fix/scaling-and-tests`.

## Key Changes from Upstream

### PR #284: KiCad 9 ERC Fixes
- Pin UUID generation for connectivity
- Wire splitting at junctions
- Quote escaping in S-expressions
- mm/mils boundary conversion

### Auto-Stub + ERC Correction Loop (this branch)
Opt-in via `generate_schematic(auto_stub=True)`. Three-phase approach:

1. **Pre-generation heuristics** (`auto_stub_nets()` in `gen_schematic.py`):
   - Power nets (GND, VCC, +3V3, etc.) → global labels
   - High-fanout nets (>= threshold) → global labels
   - User-explicit `net.stub = True/False` always respected

2. **Cross-group stubbing** (`_auto_stub_cross_group()` in `place.py`):
   - Nets spanning multiple placement groups → global labels
   - Runs after `group_parts()`, then re-groups

3. **ERC correction loop** (in `gen_schematic.py`):
   - After generation: `kicad-cli sch erc` → parse errors → stub problem nets → full regenerate
   - Up to `erc_max_iterations` passes (default 3)
   - Each regeneration tries expansion (1.0x → 1.5x → 2.25x) before fallback

### Bug Fixes
- **NetTerminal cross-circuit**: `NetTerminal.__init__` now passes `circuit=net.circuit` to `Part.__init__` so it works with explicit `Circuit()` objects
- **ERC loop routing failure**: Inner regeneration handles `RoutingFailure` gracefully

## Options

```python
generate_schematic(
    auto_stub=True,              # Enable all auto-stub features
    auto_stub_fanout=5,          # High-fanout threshold (default 5)
    erc_max_iterations=3,        # Max ERC correction passes (default 3)
    auto_stub_fallback="labels", # "labels" | "raise" | "warn"
)
```

### Fallback Policy (`auto_stub_fallback`)
- `"labels"` (default) — produces labels-only schematic + WARNING listing converted nets
- `"raise"` — re-raises RoutingFailure so caller sees it (use for debugging)
- `"warn"` — labels-only output + Python `LabelsOnlyWarning` exception

## File Map

| File | What Changed |
|------|-------------|
| `src/skidl/net.py` | `_stub_explicit` tracking in `__init__` and `stub.setter` |
| `src/skidl/tools/kicad9/gen_schematic.py` | `auto_stub_nets()`, ERC loop, `_handle_fallback()`, `_parse_erc_report()` |
| `src/skidl/schematics/place.py` | `_auto_stub_cross_group()` after `group_parts()` |
| `src/skidl/schematics/net_terminal.py` | Pass `circuit=net.circuit` to `Part.__init__` |
| `tests/unit_tests/ai_tests/test_auto_stub.py` | 48 tests across 3 layers |

## Testing

```bash
# All auto-stub tests (unit + integration + KiCad CLI)
KICAD9_SYMBOL_DIR=/usr/share/kicad/symbols .venv/bin/python -m pytest tests/unit_tests/ai_tests/test_auto_stub.py -v

# Full AI test suite (regression check)
KICAD9_SYMBOL_DIR=/usr/share/kicad/symbols .venv/bin/python -m pytest tests/unit_tests/ai_tests/ -v
```

Pre-existing failures (not ours): `test_generate_svg` (missing netlistsvg), `test_generate_pcb` (missing FootprintLoad).

## Venv

- SKiDL dev venv: `/home/lachlan/Projects/skidl/.venv/` (Python 3.12, editable install)
- Concentric PCB venv: `/home/lachlan/Projects/concentric/.venv-pcb/` (created on macOS, broken on wintermute)
- KiCad 9 symbols: `/usr/share/kicad/symbols` (set via `KICAD9_SYMBOL_DIR`)

## SKiDL Internals Cheat Sheet

- `net.valid` is a property (not `is_valid()`)
- `net._stub` is the backing field; `net.stub` is the property with setter that propagates to pins
- `Part.__init__` uses `circuit = circuit or default_circuit` — always pass circuit explicitly for non-default circuits
- `NetTerminal` is a specialized Part with one pin, used for net labels in schematics
- `SchNode.get_internal_nets()` skips stubbed pins (line 217)
- `Placer.group_parts()` groups parts by non-stub net connectivity
- Routing engine: tries switchbox routing, raises `RoutingFailure` on failure
- `finalize_parts_and_nets()` removes NetTerminals and cleans up placement attrs — must call after every place/route attempt
